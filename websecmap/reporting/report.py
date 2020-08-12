import logging
from collections import defaultdict
from copy import copy, deepcopy
from datetime import datetime
from typing import List

import pytz
from django.db.models import Q

from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.reporting.models import UrlReport
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)


START_DATE = datetime(year=2016, month=1, day=1, hour=13, minute=37, second=42, tzinfo=pytz.utc)

"""
Warning: Make sure the output of a rebuild has ID's in chronological order.

This code doesn't understand anything else than urls.
"""


def get_allowed_to_report():
    """
    Retrieves from settings what scan types will be included in the report.

    :return:
    """

    allowed_to_report = []

    for scan_type in ALL_SCAN_TYPES:
        if constance_cached_value('REPORT_INCLUDE_' + scan_type.upper()):
            allowed_to_report.append(scan_type)

    return allowed_to_report


@app.task(queue='reporting')
def recreate_url_reports(urls: List):
    """Remove the rating of one url and rebuild anew."""

    for url in urls:
        # Delete the ratings for this url, they are going to be rebuilt
        UrlReport.objects.all().filter(url=url).delete()

        # Creating a timeline and rating it is much faster than doing an individual calculation.
        # Mainly because it gets all data in just a few queries and then builds upon that.
        create_url_report(create_timeline(url), url)


def significant_moments(urls: List[Url] = None, reported_scan_types: List[str] = None):
    """
    Searches for all significant point in times that something changed. The goal is to save
    unneeded queries when rebuilding ratings. When you know when things changed, you know
    at what moments you need to create reports.

    Another benefit is not only less queries, as all relevant scans , but also more granularity for reporting: not just
    per week, but known per day.

    We want to know:
    - When a rating was made, since only changes are saved, all those datapoints.
    - - This implies when the url was alive (at least after a positive result).
    - When a url was not resolvable (aka: is not in the report anymore)

    Note: something is considered alive again after a scan has been found on the endpoint or url.

    :return:
    """

    log.debug("Making a timeline for %s urls: %s" % (len(urls), urls))

    if not urls:
        log.info("No urls, so no moments")
        return []

    # since we want to know all about these endpoints, get them at the same time, which is faster.
    # Otherwise related objects where requested at create timeline.
    # Difference:
    # before prefetch: 878 calls in 23411 ms = 26.66 ms / call
    # after prefetch: 1373 calls in 22636 ms = 16.48 ms / call
    # test: 420 in 4629 = 11ms / call
    # A nearly 40% performance increase :)
    # the red flag was there was a lot of "__get__" operations going on inside create timeline, while it doesn't do sql
    # after the update no calls to __get__ at all.
    # qualys_rating=0 means "Unable to connect to the server" and is not returned with a score. This happens in old
    # datasets.
    # we don't store tls_qualys scans in a separate table anymore
    # SEPT 2019: sqlite is affected by SQLITE_LIMIT_VARIABLE_NUMBER with IN queries. For larger datasets
    # This approach will fail during development.
    endpoint_scans = EndpointGenericScan.objects.all().filter(type__in=reported_scan_types, endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    endpoint_scans = latest_rating_per_day_only(endpoint_scans)
    endpoint_scan_dates = [x.rating_determined_on for x in endpoint_scans]

    url_scans = UrlGenericScan.objects.all().filter(type__in=reported_scan_types, url__in=urls).\
        prefetch_related("url")
    url_scans = latest_rating_per_day_only(url_scans)
    url_scan_dates = [x.rating_determined_on for x in url_scans]

    dead_endpoints = Endpoint.objects.all().filter(url__in=urls, is_dead=True)
    dead_scan_dates = [x.is_dead_since for x in dead_endpoints]

    non_resolvable_urls = Url.objects.filter(not_resolvable=True, url__in=urls)
    non_resolvable_dates = [x.not_resolvable_since for x in non_resolvable_urls]

    dead_urls = Url.objects.filter(is_dead=True, url__in=urls)
    dead_url_dates = [x.is_dead_since for x in dead_urls]

    # reduce this to one moment per day only, otherwise there will be a report for every change
    # which is highly inefficient. Using the latest possible time of the day is used.
    moments = endpoint_scan_dates + url_scan_dates + non_resolvable_dates + \
        dead_scan_dates + dead_url_dates
    moments = [latest_moment_of_datetime(x) for x in moments]
    moments = sorted(set(moments))

    # If there are no scans at all, just return instead of storing useless junk or make other mistakes
    if not moments:
        return [], {
            'endpoint_scans': [],
            'url_scans': [],
            'dead_endpoints': [],
            'non_resolvable_urls': [],
            'dead_urls': []
        }

    # make sure you don't save the scan for today at the end of the day (which would make it visible only at the end
    # of the day). Just make it "now" so you can immediately see the results.
    if moments[-1] == latest_moment_of_datetime(datetime.now()):
        moments[-1] = datetime.now(pytz.utc)

    # log.debug("Moments found: %s", len(moments))

    # using scans, the query of "what scan happened when" doesn't need to be answered anymore.
    # the one thing is that scans have to be mapped to the moments (called a timeline)
    happenings = {
        'endpoint_scans': endpoint_scans,
        'url_scans': url_scans,
        'dead_endpoints': dead_endpoints,
        'non_resolvable_urls': non_resolvable_urls,
        'dead_urls': dead_urls
    }
    # count_queries()
    return moments, happenings


def latest_rating_per_day_only(scans):
    """
    Update 12 nov 2018: If there are multiple changes per day on the url on the same issue, this might not give the
    correct results yet. For example: DNSSEC was scanned as ERROR and INFO on Nov 5 2018. Both are retrieved. Due to
    some reason, the ERROR one gets in the report, while the last_scan_moment of the INFO one is more recent.
    The one with the highest last_scan_moment (the newest) should be added to the report, the other one can be
    ignored.

    Example input:
    ID      Last Scan Moment            Rating Determined On      Type      Rating
    Scan 1  Nov. 12, 2018, 12:15 a.m.	Nov. 5, 2018, 3:25 p.m.   DNSSEC    INFO
    Scan 2  Nov. 5, 2018, 12:06 p.m.	Nov. 5, 2018, 12:06 p.m.  DNSSEC    ERROR

    Result:
    Scan 1  Nov. 12, 2018, 12:15 a.m.	Nov. 5, 2018, 3:25 p.m.   DNSSEC    INFO

    :param scans: You'll get all the scans, for all dates and multiple types.
    :return: All scans, for all dates and multiple types, with the scan with the highest scan moment per type+date

    Actually the reporting code is optimized to filter out double scans for a single day, and it takes the last one.
    But still we want to be sure the result is clean. Does that mean we can only accept one report per day?
    Why? There are multiple moments and multiple dates. And one scan always comes after the other.

    So why do we only have one report per day. And why is the rating_determined_on ignored?
    We do this otherwise every change would lead to a new report, which generates an enormous growth in the number
    of reports. To give an impression:

    On Novemer 2018 the following is in the database:
    URL Generic Scans: 1850
    TLS Scans: 29345
    Endpoint generic scans: 173998
    TOTAL: 205.193 changes in scans. Would we create a report containing each of these changes, we'd have the same
    amount of reports.

    Using reduction per day, we only have a total of 61377 URL ratings, which is about a fourth of the total and
    it only has 24252 organization ratings, which is just over 10%. An organization rating of Rotterdam is about
    1.5 megabyte of JSON in total. (<1 Megabyte without the whitespace). Would an average rating be 500 KB:
    500000kb * 24252 reports = 12126000000kb = 12.126 gigabyte. (with compression etc) it is now just ±1 gigabyte.

    So imagine it's 10x more, the DB would be 10 gigabyte at least: all to have a minute accuracy improvement which
    basically nobody cares about. A day resolution is more than enough.

    This is the reason functions like this exist, to just help and optimize the amount of storage.

    It's possible to have scans from a series of endpoints/urls.
    """
    # we don't want to care about the order the scans came in: it can by any set of scans in any order, and it will
    # get the correct result quickly. For this we use a hash table of all scans, matched with the scan.

    hash_table = []
    # build the hash table
    for scan in scans:
        # A combination that is unique, enough to identify a scan, but that will cause a collision if we don't
        # filter out the problematic values.
        hash = hash_scan_per_day_and_type(scan)
        # use a high precision here, since we want to have the absolute latest scan
        # only when a rating changes, a new scan is added, this makes it fairly easy to get the latest
        if not in_hash_table(hash_table, hash):
            hash_table.append({'hash': hash, 'scan': scan})
        else:
            # here is where the magic happens: only the scan with the highest rating_determined_on can stay
            # find the one, check it and replace it.
            existing_item = in_hash_table(hash_table, hash)
            if existing_item['scan'].rating_determined_on < scan.rating_determined_on:
                # Due to the ordering of the scans, usually this message will NEVER appear and the first scan
                # was always the latest. Perhaps per database this default ordering differs. Since we don't have
                # testcases, i don't dare to touch the rest of this code.
                log.debug("Scan ID %s on %s had also another scan today that had a rating that lasted longer."
                          % (scan.pk, scan.type))
                hash_table.remove(existing_item)
                hash_table.append({'hash': hash, 'scan': scan})
            else:
                log.debug("Scan ID %s on %s had also another scan today that had a rating that lasted shorter. IGNORED"
                          % (scan.pk, scan.type))

    # return a list of scans:
    filtered_scans = []
    for hash in hash_table:
        filtered_scans.append(hash['scan'])

    return filtered_scans


def in_hash_table(hash_table, hash):
    # https://stackoverflow.com/questions/8653516/python-list-of-dictionaries-search
    try:
        return next((item for item in hash_table if item['hash'] == hash))

    except StopIteration:
        return False


def hash_scan_per_day_and_type(scan):

    # hopefully it doesn't run extra queries?
    if scan.type in URL_SCAN_TYPES:
        pk = scan.url.pk
    else:
        pk = scan.endpoint.pk

    return "%s%s%s" % (pk, scan.type, scan.rating_determined_on.replace(second=59, microsecond=999999))


def create_timeline(url: Url):
    """
    Maps happenings to moments.

    This is used to save database queries: when you know at what moment things change and what happened before,
    you only need to save the changes over time and remember what happened before. This approach increases the speed
    of url ratings to over 80%.

    It is more than enough to have just one set of changes per day.

    A timeline looks like this:
    date - things that changed

    01-01-2017 - endpoint added

    01-02-2017 - TLS scan Update
    01-04-2017 - TLS scan update
                 HTTP Scan update

    :return:
    """
    moments, happenings = significant_moments(urls=[url], reported_scan_types=get_allowed_to_report())

    timeline = {}

    # reduce to date only, it's not useful to show 100 things on a day when building history.
    for moment in moments:
        moment_date = moment.replace(second=59, microsecond=999999)
        timeline[moment_date] = {}
        timeline[moment_date]['endpoints'] = []
        timeline[moment_date]['endpoint_scans'] = []
        timeline[moment_date]['url_scans'] = []
        timeline[moment_date]['dead_endpoints'] = []
        timeline[moment_date]['urls'] = []

    # sometimes there have been scans on dead endpoints. This is a problem in the database.
    # this code is correct with retrieving those endpoints again.
    # we could save a list of dead endpoints, but the catch is that an endpoint can start living
    # again over time. The scans with only dead endpoints should not be made.

    for scan in happenings['endpoint_scans']:
        some_day = scan.rating_determined_on.replace(second=59, microsecond=999999)

        # can we create this set in an easier way?
        if "endpoint_scan" not in timeline[some_day]:
            timeline[some_day]['endpoint_scan'] = {'scans': [], 'endpoints': []}

        # timeline[some_day]['endpoint_scan']['scanned'] = True  # do we ever check on this? Seems not.
        timeline[some_day]['endpoint_scan']['scans'].append(scan)
        timeline[some_day]['endpoint_scan']['endpoints'].append(scan.endpoint)
        timeline[some_day]['endpoints'].append(scan.endpoint)
        timeline[some_day]['endpoint_scans'].append(scan)

    for scan in happenings['url_scans']:
        some_day = scan.rating_determined_on.replace(second=59, microsecond=999999)

        # can we create this set in an easier way?
        if "url_scan" not in timeline[some_day]:
            timeline[some_day]['url_scan'] = {'scans': [], 'urls': []}

        # timeline[some_day]['endpoint_scan']['scanned'] = True  # do we ever check on this? Seems not.
        timeline[some_day]['url_scan']['scans'].append(scan)
        timeline[some_day]['url_scan']['urls'].append(scan.url)
        timeline[some_day]['urls'].append(scan.url)
        timeline[some_day]['url_scans'].append(scan)

    # Any endpoint from this point on should be removed. If the url becomes alive again, add it again, so you can
    # see there are gaps in using the url over time. Which is more truthful.
    for moment in [not_resolvable_url.not_resolvable_since for not_resolvable_url in happenings['non_resolvable_urls']]:
        timeline[moment.replace(second=59, microsecond=999999)]['url_not_resolvable'] = True

    for moment in [dead_url.is_dead_since for dead_url in happenings['dead_urls']]:
        timeline[moment.replace(second=59, microsecond=999999)]['url_is_dead'] = True

    for endpoint in happenings['dead_endpoints']:
        some_day = endpoint.is_dead_since.replace(second=59, microsecond=999999)
        timeline[some_day]['dead'] = True
        if endpoint not in timeline[some_day]['dead_endpoints']:
            timeline[some_day]['dead_endpoints'].append(endpoint)

    # unique endpoints only
    for moment in moments:
        some_day = moment.replace(second=59, microsecond=999999)
        timeline[some_day]['endpoints'] = list(set(timeline[some_day]['endpoints']))

    # try to return dates in chronological order
    return timeline


def latest_moment_of_datetime(datetime_: datetime):
    return datetime_.replace(second=59, microsecond=999999, tzinfo=pytz.utc)


def create_url_report(timeline, url: Url):
    """
    This creates:
    {
        "url": ...,
        "ratings": [
            {Rating 1}, {Rating 2}
            ],
        "endpoints":
        {...
        "Ratings": {Rating1, Rating 2...


    :param timeline:
    :param url:
    :return:
    """

    log.info("Rebuilding ratings for url %s on %s moments" % (url, len(timeline)))
    previous_endpoint_ratings = {}
    previous_url_ratings = {}
    previous_endpoints = []
    url_was_once_rated = False
    dead_endpoints = set()

    # work on a sorted timeline as otherwise this code is non-deterministic!
    for moment in sorted(timeline):
        given_ratings = {}

        if ('url_not_resolvable' in timeline[moment] or 'url_is_dead' in timeline[moment]) \
                and url_was_once_rated:
            log.debug('Url became non-resolvable or dead. Adding an empty rating to lower the score of'
                      'this domain if it had a score. It has been cleaned up. (hooray)')
            # this is the end for the domain.
            default_calculation = {
                "url": url.url,
                "ratings": [],
                "endpoints": [],
            }

            save_url_report(url, moment, default_calculation)
            return

        # reverse the relation: so we know all ratings per endpoint.
        # It is not really relevant what endpoints _really_ exist.
        endpoint_scans = {}
        for scan in timeline[moment]['endpoint_scans']:
            endpoint_scans[scan.endpoint.id] = []

        for scan in timeline[moment]['endpoint_scans']:
            endpoint_scans[scan.endpoint.id].append(scan)

        # create the report for this moment
        endpoint_calculations = []

        # also include all endpoints from the past time, which we do until the endpoints are dead.
        relevant_endpoints = set(timeline[moment]['endpoints'] + previous_endpoints)

        # remove dead endpoints
        # we don't need to remove the previous ratings, unless we want to save memory (Nah :))
        if "dead_endpoints" in timeline[moment]:
            for dead_endpoint in timeline[moment]['dead_endpoints']:

                # make sure that scan results are never added to dead endpoints.
                # this can happen when a scan result is stored or performed _after_ the endpoint is declared dead
                # as the endpoint is dead, no new scans will be added to it, overwriting the data.
                # this causes stale results to show up in the report.
                # Endpoints cannot be revived, so we can safely ignore all scan results from dead_endpoints.
                dead_endpoints.add(dead_endpoint)

                # endpoints can die this moment,
                # note that this removes only once. if the endpoint was rated twice with the same rating, the older one
                # is still in there. Therefore it's not an IF but a WHILE statement.
                while dead_endpoint in relevant_endpoints:
                    relevant_endpoints.remove(dead_endpoint)
                # remove the endpoint from the past
                while dead_endpoint in previous_endpoints:
                    previous_endpoints.remove(dead_endpoint)

        # do not do things with endpoints that have died.
        # see: test_data_from_dead_endpoint_stays_gone
        # how can it be that the dead endpoint is still in relevant endpoints (because of previous endpoints.?
        # do this before the below loop, otherwise endpoint might be assigned with the wrong value and then
        # continued?
        for dead_endpoint in list(dead_endpoints):
            # prevent KeyError
            if dead_endpoint in relevant_endpoints:
                relevant_endpoints.remove(dead_endpoint)

        for endpoint in relevant_endpoints:
            # All endpoints of all time are iterated. The dead endpoints etc should be filtered out above.
            url_was_once_rated = True

            calculations = []
            these_endpoint_scans = {}
            if endpoint.id in endpoint_scans:
                for scan in endpoint_scans[endpoint.id]:
                    if scan.type in ENDPOINT_SCAN_TYPES:
                        these_endpoint_scans[scan.type] = scan

            # enrich the ratings with previous ratings, without overwriting them.
            for endpoint_scan_type in ENDPOINT_SCAN_TYPES:
                if all([endpoint_scan_type not in these_endpoint_scans,
                        endpoint_scan_type in previous_endpoint_ratings.get(endpoint.id, [])]):
                    these_endpoint_scans[endpoint_scan_type] = previous_endpoint_ratings[endpoint.id][
                        endpoint_scan_type]

            # propagate the ratings to the next iteration.
            previous_endpoint_ratings[endpoint.id] = these_endpoint_scans

            # build the calculation:
            #
            # a scan/rating can only happen one time per port on a moment, regardless of endpoint.
            #
            # it is saved multiple times to the database, due to qualys finding multiple IP
            # adresses. In turn other scanners think these endpoints also are reachable, when they
            # in fact are not (behind a load balancer, or whatever).
            #
            # I've no clue how qualys can think they can reach the website over a different IP
            # forefully.
            # EG: webmail.zaltbommel.nl (microsoft hosted(!)) has eight endpoints: 4 on v4 and v6
            #
            # To fix this, confusingly, give only one rating to the endpoint. And then add a
            # "repeated" message, so you know a rating is repeated, and didn't get extra points.
            # january 2020: the protocol was not added in the comparison. In the internet.nl dashboard
            # the protocol is the thing that makes the difference between endpoints as all endpoints
            # are on IP version 0 and port 0 (they are semi real endpoints)
            label = str(moment) + str(endpoint.is_ipv6()) + str(endpoint.port) + str(endpoint.protocol)
            if label not in given_ratings:
                # todo: this can be a defaultdict
                given_ratings[label] = []

            for endpoint_scan_type in ENDPOINT_SCAN_TYPES:
                if endpoint_scan_type in these_endpoint_scans:
                    if endpoint_scan_type not in given_ratings[label]:
                        calculations.append(get_severity(these_endpoint_scans[endpoint_scan_type]))

                        given_ratings[label].append(endpoint_scan_type)
                    else:
                        # should we just remove the repeated findings? There should not be one of these anyone
                        # anymore...
                        calculations.append({
                            "type": endpoint_scan_type,
                            "explanation": "Repeated finding. Probably because this url changed IP adresses or has "
                                           "multiple IP adresses (common for failover / load-balancing).",
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                            "ok": 0,
                            "not_applicable": 0,
                            "not_testable": 0,
                            "error_in_test": 0,
                            "since": these_endpoint_scans[endpoint_scan_type].rating_determined_on.isoformat(),
                            "last_scan": these_endpoint_scans[endpoint_scan_type].last_scan_moment.isoformat(),

                            # With this empty calculation, make sure all standard fields are available.
                            'is_explained': False,
                            'comply_or_explain_explanation': '',
                            'comply_or_explain_explained_on': '',
                            'comply_or_explain_explanation_valid_until': '',
                            'comply_or_explain_valid_at_time_of_report': False
                        })

            # Readibility is important: it's ordered from the worst to least points.
            calculations = sorted(calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)
            endpoint_calculations.append(create_endpoint_calculation(endpoint, calculations))

        previous_endpoints += relevant_endpoints

        # Add url generic scans, using the same logic as endpoints.
        # - It reuses ratings from the previous moment, but if there are new ratings for a specific scan type only the
        # rating for this specific scan type is overwritten.
        # - Dead and not resolvable urls have been checked above, which helps.
        url_scans = defaultdict(list)
        for scan in timeline[moment]['url_scans']:
            url_scans[scan.url.id].append(scan)

        url_calculations = []
        these_url_scans = {}
        url_scan_types = URL_SCAN_TYPES

        if url.id in url_scans:
            for scan in url_scans[url.id]:
                if scan.type in URL_SCAN_TYPES:
                    these_url_scans[scan.type] = scan

        # enrich the ratings with previous ratings, which saves queries.
        for url_scan_type in url_scan_types:
            if all([
                url_scan_type not in these_url_scans,
                url_scan_type in previous_url_ratings.get(url.id, [])
            ]):
                these_url_scans[url_scan_type] = previous_url_ratings[url.id][url_scan_type]

        # propagate the ratings to the next iteration.
        previous_url_ratings[url.id] = these_url_scans

        for url_scan_type in url_scan_types:
            if url_scan_type in these_url_scans:
                url_calculations.append(get_severity(these_url_scans[url_scan_type]))

        # prevent empty ratings cluttering the database and skewing the stats.
        # todo: only do this if there never was a urlrating before this.
        if not endpoint_calculations and not url_was_once_rated and not url_calculations:
            continue

        calculation = {
            "url": url.url,
            "ratings": url_calculations,
            "endpoints": endpoint_calculations,
        }

        log.debug("On %s %s has %s endpoints." % (moment, url, len(endpoint_calculations)))

        save_url_report(url, moment, calculation)


def create_endpoint_calculation(endpoint, calculations):
    return {
        "id": endpoint.pk,
        "concat": "%s/%s IPv%s" % (endpoint.protocol, endpoint.port, endpoint.ip_version),
        "ip": endpoint.ip_version,
        "ip_version": endpoint.ip_version,
        "port": endpoint.port,
        "protocol": endpoint.protocol,
        "v4": endpoint.is_ipv4(),
        "ratings": calculations
    }


def add_report_to_key(amount_of_issues, key, report):
    """
    Simply combines numbers from reports into categories.

    :param amount_of_issues:
    :param key:
    :param report:
    :return:
    """

    amount_of_issues[key]['high'] += report['high']
    amount_of_issues[key]['medium'] += report['medium']
    amount_of_issues[key]['low'] += report['low']
    amount_of_issues[key]['any'] += (report['low'] + report['medium'] + report['high'])
    amount_of_issues[key]['ok'] += report['ok']

    # Only overall, endpoint and url contain not_testable and not_applicable values.
    # This is due something being explained. Perhaps over time we want to also explain not_testable things?
    # No judgement is needed on these values, as it has no effect on high, mids or low?
    if key in ['overall', 'endpoint', 'url']:
        amount_of_issues[key]['not_testable'] += report['not_testable']
        amount_of_issues[key]['not_applicable'] += report['not_applicable']
        amount_of_issues[key]['error_in_test'] += report['error_in_test']

    return amount_of_issues


def judge(amount_of_issues, clean_issues_for_judgement, key, reports: List):
    # All reports for the endpoint can determine a judgement for the endpoint. For example, if all endpoint reports
    # say that the result is ok. The endpoint itself becomes 'ok'.

    judgement_issues = deepcopy(clean_issues_for_judgement)

    for report in reports:
        judgement_issues = add_report_to_key(judgement_issues, key, report)

    # Now we know the statistics for the endpoint, we can add a judgement to the endpoint.
    if judgement_issues[key]['high']:
        amount_of_issues[key + '_judgements']['high'] += 1
        return amount_of_issues, judgement_issues

    if judgement_issues[key]['medium']:
        amount_of_issues[key + '_judgements']['medium'] += 1
        return amount_of_issues, judgement_issues

    if judgement_issues[key]['low']:
        amount_of_issues[key + '_judgements']['low'] += 1
        return amount_of_issues, judgement_issues

    if judgement_issues[key]['ok']:
        amount_of_issues[key + '_judgements']['ok'] += 1
        return amount_of_issues, judgement_issues

    # nothing is set? weird... no. Because explained can be zero if things are not explained.
    return amount_of_issues, judgement_issues


def statistics_over_url_calculation(calculation):

    empty_with_some_extras = {'high': 0, 'medium': 0, 'low': 0, 'any': 0, 'ok': 0,
                              'not_testable': 0, 'not_applicable': 0, 'error_in_test': 0}

    empty = {'high': 0, 'medium': 0, 'low': 0, 'any': 0, 'ok': 0}

    # Calculate statistics here, instead of working with all kinds of variables.
    amount_of_issues = {
        'overall': copy(empty_with_some_extras),
        'overall_explained': copy(empty),

        # sum of all issues on the url level
        'url': copy(empty_with_some_extras),
        'url_explained': copy(empty),

        # sum of all issues in endpoints
        'endpoint': copy(empty_with_some_extras),
        'endpoint_explained': copy(empty),

        # judgements are complex situation: when ALL reports of an endpoint say the endpoint is OK, a single
        # judgement is added for that endpoint. There are multiple endpoints with multiple judgements.
        'endpoint_judgements': copy(empty),
        # Some reports will be explained, that means the endpoint will be explained on a certain level.
        'endpoint_explained_judgements': copy(empty),

        # As there is only one url, with multiple reports, only one judgement will be made.
        'url_judgements': copy(empty),
        'url_explained_judgements': copy(empty),

        # If there is a single high endpoint judgement, or a single high url judgement, the overall is high.
        # This can have a maximum of 1 value, which summarizes all url_judgements and endpoint_judgements
        'overall_judgements': copy(empty),
    }

    clean_issues_for_judgement = deepcopy(amount_of_issues)

    for i, endpoint in enumerate(calculation['endpoints']):

        # Simply sum numbers.
        for report in endpoint['ratings']:
            if report['is_explained']:
                amount_of_issues = add_report_to_key(amount_of_issues, 'endpoint_explained', report)
            else:
                amount_of_issues = add_report_to_key(amount_of_issues, 'endpoint', report)

        amount_of_issues, judgement_issues = judge(
            amount_of_issues, clean_issues_for_judgement, 'endpoint', [amount_of_issues['endpoint']])
        amount_of_issues, explained_judgement_issues = judge(
            amount_of_issues, clean_issues_for_judgement, 'endpoint_explained',
            [amount_of_issues['endpoint_explained']])

        # inject statistics inside the calculation per endpoint.
        calculation['endpoints'][i]['high'] = judgement_issues['endpoint']['high']
        calculation['endpoints'][i]['medium'] = judgement_issues['endpoint']['medium']
        calculation['endpoints'][i]['low'] = judgement_issues['endpoint']['low']
        calculation['endpoints'][i]['ok'] = judgement_issues['endpoint']['ok']
        calculation['endpoints'][i]['explained_high'] = explained_judgement_issues['endpoint_explained']['high']
        calculation['endpoints'][i]['explained_medium'] = explained_judgement_issues['endpoint_explained']['medium']
        calculation['endpoints'][i]['explained_low'] = explained_judgement_issues['endpoint_explained']['low']

    for report in calculation['ratings']:
        if report['is_explained']:
            amount_of_issues = add_report_to_key(amount_of_issues, 'url_explained', report)
        else:
            amount_of_issues = add_report_to_key(amount_of_issues, 'url', report)

    amount_of_issues, clean = judge(amount_of_issues, clean_issues_for_judgement, 'url', [amount_of_issues['url']])
    amount_of_issues, clean = judge(
        amount_of_issues, clean_issues_for_judgement, 'url_explained', [amount_of_issues['url_explained']])

    # and to calculate the overall, we can use the same routine, as the same keys are available.
    amount_of_issues = add_report_to_key(amount_of_issues, 'overall', amount_of_issues['url'])
    amount_of_issues = add_report_to_key(amount_of_issues, 'overall', amount_of_issues['endpoint'])

    amount_of_issues = add_report_to_key(amount_of_issues, 'overall_explained', amount_of_issues['url_explained'])
    amount_of_issues = add_report_to_key(amount_of_issues, 'overall_explained', amount_of_issues['endpoint_explained'])

    # and determine the final judgement: Not used yet.
    if amount_of_issues['endpoint_judgements']['high'] or amount_of_issues['url_judgements']['high']:
        amount_of_issues['overall_judgements']['high'] = 1
    elif amount_of_issues['endpoint_judgements']['medium'] or amount_of_issues['url_judgements']['medium']:
        amount_of_issues['overall_judgements']['medium'] = 1
    elif amount_of_issues['endpoint_judgements']['low'] or amount_of_issues['url_judgements']['low']:
        amount_of_issues['overall_judgements']['low'] = 1
    elif amount_of_issues['endpoint_judgements']['ok'] or amount_of_issues['url_judgements']['ok']:
        amount_of_issues['overall_judgements']['ok'] = 1

    return calculation, amount_of_issues


def save_url_report(url: Url, date: datetime, calculation):

    # This also injects the statistics into the json, for use in representations / views in the right places.
    calculation, amount_of_issues = statistics_over_url_calculation(calculation)

    u = UrlReport()
    u.url = url

    # save it as NOW if it's done today, else on the last moment on the same day.
    # So the url ratings immediately are shown, even if the day is not over.
    if date == datetime.now().date():
        u.at_when = datetime.now(pytz.utc)
    else:
        u.at_when = datetime(year=date.year, month=date.month, day=date.day,
                             hour=date.hour, minute=date.minute,
                             second=59, microsecond=999999, tzinfo=pytz.utc)

    u.total_endpoints = len(calculation['endpoints'])

    u.high = amount_of_issues['overall']['high']
    u.medium = amount_of_issues['overall']['medium']
    u.low = amount_of_issues['overall']['low']
    u.total_issues = amount_of_issues['overall']['any']
    u.ok = amount_of_issues['overall']['ok']
    u.not_testable = amount_of_issues['overall']['not_testable']
    u.not_applicable = amount_of_issues['overall']['not_applicable']
    u.error_in_test = amount_of_issues['overall']['error_in_test']

    u.high_endpoints = amount_of_issues['endpoint_judgements']['high']
    u.medium_endpoints = amount_of_issues['endpoint_judgements']['medium']
    u.low_endpoints = amount_of_issues['endpoint_judgements']['low']
    u.ok_endpoints = amount_of_issues['endpoint_judgements']['ok']

    u.total_url_issues = amount_of_issues['url']['any']
    u.total_endpoint_issues = amount_of_issues['endpoint']['any']

    u.url_issues_high = amount_of_issues['url']['high']
    u.url_issues_medium = amount_of_issues['url']['medium']
    u.url_issues_low = amount_of_issues['url']['low']
    u.url_not_testable = amount_of_issues['url']['not_testable']
    u.url_not_applicable = amount_of_issues['url']['not_applicable']
    u.url_error_in_test = amount_of_issues['url']['error_in_test']

    # probably the same as OK, as you can only be OK once.
    u.url_ok = amount_of_issues['overall_judgements']['ok']

    u.endpoint_issues_high = amount_of_issues['endpoint']['high']
    u.endpoint_issues_medium = amount_of_issues['endpoint']['medium']
    u.endpoint_issues_low = amount_of_issues['endpoint']['low']
    u.endpoint_ok = amount_of_issues['endpoint']['ok']
    u.endpoint_not_testable = amount_of_issues['endpoint']['not_testable']
    u.endpoint_not_applicable = amount_of_issues['endpoint']['not_applicable']
    u.endpoint_error_in_test = amount_of_issues['endpoint']['error_in_test']

    u.explained_high = amount_of_issues['url_explained_judgements']['high']
    u.explained_medium = amount_of_issues['url_explained_judgements']['medium']
    u.explained_low = amount_of_issues['url_explained_judgements']['low']

    u.explained_total_issues = amount_of_issues['overall_explained']['any']

    u.explained_high_endpoints = amount_of_issues['endpoint_explained_judgements']['high']
    u.explained_medium_endpoints = amount_of_issues['endpoint_explained_judgements']['medium']
    u.explained_low_endpoints = amount_of_issues['endpoint_explained_judgements']['low']

    u.explained_total_url_issues = amount_of_issues['url_explained']['any']
    u.explained_total_endpoint_issues = amount_of_issues['endpoint_explained']['any']
    u.explained_url_issues_high = amount_of_issues['url_explained']['high']
    u.explained_url_issues_medium = amount_of_issues['url_explained']['medium']
    u.explained_url_issues_low = amount_of_issues['url_explained']['low']
    u.explained_endpoint_issues_high = amount_of_issues['endpoint_explained']['high']
    u.explained_endpoint_issues_medium = amount_of_issues['endpoint_explained']['medium']
    u.explained_endpoint_issues_low = amount_of_issues['endpoint_explained']['low']

    calculation['ratings'] = sorted(calculation['ratings'], key=lambda k: (k['high'], k['medium'], k['low']),
                                    reverse=True)
    calculation['endpoints'] = sorted(calculation['endpoints'], key=lambda k: (k['high'], k['medium'], k['low']),
                                      reverse=True)

    # all statistics, except for endpoints can be added at the end of the json
    calculation = add_statistics_to_calculation(calculation, amount_of_issues)
    u.calculation = calculation

    u.save()


def add_statistics_to_calculation(calculation, amount_of_issues):

    # inject all kinds of statistics inside the json for easier(?) representation.
    calculation['total_issues'] = amount_of_issues['overall']['any']
    calculation['high'] = amount_of_issues['overall']['high']
    calculation['medium'] = amount_of_issues['overall']['medium']
    calculation['low'] = amount_of_issues['overall']['low']
    calculation['ok'] = amount_of_issues['overall']['ok']
    calculation['total_endpoints'] = len(calculation['endpoints'])
    calculation['high_endpoints'] = amount_of_issues['endpoint_judgements']['high']
    calculation['medium_endpoints'] = amount_of_issues['endpoint_judgements']['medium']
    calculation['low_endpoints'] = amount_of_issues['endpoint_judgements']['low']
    calculation['ok_endpoints'] = amount_of_issues['endpoint_judgements']['ok']
    calculation['total_url_issues'] = amount_of_issues['url']['any']
    calculation['url_issues_high'] = amount_of_issues['url']['high']
    calculation['url_issues_medium'] = amount_of_issues['url']['medium']
    calculation['url_issues_low'] = amount_of_issues['url']['low']
    calculation['url_ok'] = amount_of_issues['overall_judgements']['ok']
    calculation['total_endpoint_issues'] = amount_of_issues['endpoint']['any']
    calculation['endpoint_issues_high'] = amount_of_issues['endpoint']['high']
    calculation['endpoint_issues_medium'] = amount_of_issues['endpoint']['medium']
    calculation['endpoint_issues_low'] = amount_of_issues['endpoint']['low']
    calculation['explained_total_issues'] = amount_of_issues['overall_explained']['any']
    calculation['explained_high'] = amount_of_issues['url_explained_judgements']['high']
    calculation['explained_medium'] = amount_of_issues['url_explained_judgements']['medium']
    calculation['explained_low'] = amount_of_issues['url_explained_judgements']['low']
    calculation['explained_high_endpoints'] = amount_of_issues['endpoint_explained_judgements']['high']
    calculation['explained_medium_endpoints'] = amount_of_issues['endpoint_explained_judgements']['medium']
    calculation['explained_low_endpoints'] = amount_of_issues['endpoint_explained_judgements']['low']
    calculation['explained_total_url_issues'] = amount_of_issues['url_explained']['any']
    calculation['explained_url_issues_high'] = amount_of_issues['url_explained']['high']
    calculation['explained_url_issues_medium'] = amount_of_issues['url_explained']['medium']
    calculation['explained_url_issues_low'] = amount_of_issues['url_explained']['low']
    calculation['explained_total_endpoint_issues'] = amount_of_issues['endpoint_explained']['any']
    calculation['explained_endpoint_issues_high'] = amount_of_issues['endpoint_explained']['high']
    calculation['explained_endpoint_issues_medium'] = amount_of_issues['endpoint_explained']['medium']
    calculation['explained_endpoint_issues_low'] = amount_of_issues['endpoint_explained']['low']

    return calculation


def inspect_timeline(timeline, url: Url):
    newline = "\r\n"
    message = ""
    message += "" + newline
    message += "This timeline shows all changes over time on the following url:" + newline
    message += "Use this timeline for debugging purposes, to see what changes are registered." + newline
    message += "" + newline
    message += url.url + newline
    for moment in timeline:

        message += "|" + newline
        message += "|- %s" % moment + newline
        # for debugging
        # message += "|- %s: Contents: %s" % (moment, timeline[moment]) + newline

        if 'url_scan' in timeline[moment]:
            message += "|  |- url scan" + newline
            for item in timeline[moment]['url_scan']['scans']:
                calculation = get_severity(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'endpoint_scan' in timeline[moment]:
            message += "|  |- endpoint scan" + newline
            for item in timeline[moment]['endpoint_scan']['scans']:
                calculation = get_severity(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'dead' in timeline[moment]:
            message += "|  |- dead endpoints" + newline
            for endpoint in timeline[moment]['dead_endpoints']:
                message += "|  |  |- %s" % endpoint + newline

        if 'url_not_resolvable' in timeline[moment]:
            message += "|  |- url became not resolvable" + newline

        if 'url_is_dead' in timeline[moment]:
            message += "|  |- url died" + newline

    message += "" + newline
    # support this on command line
    # print(message) Use a command for this

    # first step to a UI
    return message


def aggegrate_url_rating_scores(url_ratings: List, only_include_issues: List[str] = None):
    """

    :param url_ratings: All url ratings that should be combined into a single report.
    :param only_include_issues: List of issue names, that will be added in the report. This can save a lot of data.
    :return:
    """

    scores = {
        'high': 0,
        'medium': 0,
        'low': 0,
        'ok': 0,

        'total_urls': 0,
        'high_urls': 0,
        'medium_urls': 0,
        'low_urls': 0,
        'ok_urls': 0,

        'explained_high': 0,
        'explained_medium': 0,
        'explained_low': 0,
        'explained_high_endpoints': 0,
        'explained_medium_endpoints': 0,
        'explained_low_endpoints': 0,
        'explained_high_urls': 0,
        'explained_medium_urls': 0,
        'explained_low_urls': 0,

        # number of issues can be higher than the number of urls or endpoints of course.
        'explained_total_url_issues': 0,
        'explained_url_issues_high': 0,
        'explained_url_issues_medium': 0,
        'explained_url_issues_low': 0,
        'explained_total_endpoint_issues': 0,
        'explained_endpoint_issues_high': 0,
        'explained_endpoint_issues_medium': 0,
        'explained_endpoint_issues_low': 0,
        'total_endpoints': 0,
        'high_endpoints': 0,
        'medium_endpoints': 0,
        'low_endpoints': 0,
        'ok_endpoints': 0,

        'total_url_issues': 0,
        'total_endpoint_issues': 0,
        'url_issues_high': 0,
        'url_issues_medium': 0,
        'url_issues_low': 0,
        'endpoint_issues_high': 0,
        'endpoint_issues_medium': 0,
        'endpoint_issues_low': 0,

        # todo: both endpoints and urls are rated.
        'urls': []
    }

    for urlrating in url_ratings:

        # done: filter out only the relevant issues in the calculations and throw away the rest.
        # done if the 'only_include_issues' has been set, all calculations are void and have to be done again
        # todo: when the calculation changed, all properties from the urlrating are void.

        if only_include_issues:
            calculation = remove_issues_from_calculation(urlrating.calculation, only_include_issues)
            # This already overrides endpoint statistics, use the calculation you get from this.
            calculation, amount_of_issues = statistics_over_url_calculation(calculation)
            # overwrite the rest of the statistics.
            calculation = add_statistics_to_calculation(calculation, amount_of_issues)
        else:
            calculation = urlrating.calculation

        # use the statistics in the calculation, as they might be changed due to a filter being applied.
        # these scores are used to update the statistics for the report.
        scores['urls'].append(calculation)

        scores['high'] += calculation['high']
        scores['medium'] += calculation['medium']
        scores['low'] += calculation['low']

        # can be many per url.
        scores['ok'] += calculation['ok']

        # can only be one per url
        scores['ok_urls'] += calculation['url_ok']

        scores['total_endpoints'] += calculation['total_endpoints']
        scores['high_endpoints'] += calculation['high_endpoints']
        scores['medium_endpoints'] += calculation['medium_endpoints']
        scores['low_endpoints'] += calculation['low_endpoints']
        scores['ok_endpoints'] += calculation['ok_endpoints']

        scores['total_url_issues'] += calculation['total_url_issues']
        scores['total_endpoint_issues'] += calculation['total_endpoint_issues']
        scores['url_issues_high'] += calculation['url_issues_high']
        scores['url_issues_medium'] += calculation['url_issues_medium']
        scores['url_issues_low'] += calculation['url_issues_low']
        scores['endpoint_issues_high'] += calculation['endpoint_issues_high']
        scores['endpoint_issues_medium'] += calculation['endpoint_issues_medium']
        scores['endpoint_issues_low'] += calculation['endpoint_issues_low']

        scores['explained_total_endpoint_issues'] += calculation['explained_total_endpoint_issues']
        scores['explained_endpoint_issues_high'] += calculation['explained_endpoint_issues_high']
        scores['explained_endpoint_issues_medium'] += calculation['explained_endpoint_issues_medium']
        scores['explained_endpoint_issues_low'] += calculation['explained_endpoint_issues_low']
        scores['explained_total_url_issues'] += calculation['explained_total_url_issues']
        scores['explained_url_issues_high'] += calculation['explained_url_issues_high']
        scores['explained_url_issues_medium'] += calculation['explained_url_issues_medium']
        scores['explained_url_issues_low'] += calculation['explained_url_issues_low']
        scores['explained_high_urls'] += 1 if calculation['explained_url_issues_high'] else 0
        scores['explained_medium_urls'] += 1 if calculation['explained_url_issues_medium'] else 0
        scores['explained_low_urls'] += 1 if calculation['explained_url_issues_low'] else 0
        scores['explained_high_endpoints'] += calculation['explained_high_endpoints']
        scores['explained_medium_endpoints'] += calculation['explained_medium_endpoints']
        scores['explained_low_endpoints'] += calculation['explained_low_endpoints']
        scores['explained_high'] += calculation['explained_high']
        scores['explained_medium'] += calculation['explained_medium']
        scores['explained_low'] += calculation['explained_low']

        scores['total_urls'] += 1

        # url can only be in one category (otherwise there are urls in multiple categories which makes it
        # hard to display)
        if calculation['high_endpoints'] or calculation['url_issues_high']:
            scores['high_urls'] += 1
        elif calculation['medium_endpoints'] or calculation['url_issues_medium']:
            scores['medium_urls'] += 1
        elif calculation['low_endpoints'] or calculation['url_issues_low']:
            scores['low_urls'] += 1

    scores['total_issues'] = scores['high'] + scores['medium'] + scores['low']

    # the score cannot be OK if there are no urls.
    # Why is this done? It seems like this is more to give a sign the score is 'perfect'
    # i thought OK would mean the number of things that are OK, so you can compare them to the not OK things (high etc)
    # What depends on this 'ok' number? Nothing would be ok like this, so my guess is nothing uses this.
    # If there would be a field for perfection, it should be named 'perfect'.
    # scores['ok'] = 0 if scores['total_issues'] else 1 if scores['total_urls'] else 0

    return scores


def remove_issues_from_calculation(calculation, issues):

    # todo: also recalculate here?
    new_url_ratings = []
    for url_rating in calculation['ratings']:
        if url_rating['type'] in issues:
            new_url_ratings.append(url_rating)
    calculation['ratings'] = new_url_ratings

    # endpoints are a bit harder, they will be removed if there are no relevant issues for the endpoint.
    new_endpoints = []
    for endpoint in calculation['endpoints']:
        new_endpoint_ratings = []
        for endpoint_rating in endpoint['ratings']:
            if endpoint_rating['type'] in issues:
                new_endpoint_ratings.append(endpoint_rating)
        if new_endpoint_ratings:
            endpoint['ratings'] = new_endpoint_ratings
            new_endpoints.append(endpoint)

    calculation['endpoints'] = new_endpoints

    return calculation


def get_latest_urlratings_fast(urls: List[Url], when):
    # one query for all items. with sql injection feature.
    # perhaps we can do UrlRating.objects.raw( to avoid json loading.

    # prevent an empty IN query
    if not urls:
        return []

    # get all columns, instead of naming each of the 20 columns separately, and having the chance that you missed one
    # and then django performs a separate lookup query for that value (a few times).
    sql = '''SELECT *
                FROM reporting_urlreport
                INNER JOIN
                  (SELECT MAX(id) as id2 FROM reporting_urlreport or2
                  WHERE at_when <= '%s' AND url_id IN (''' % (when, ) + ','.join(map(str, urls)) + ''')
                  GROUP BY url_id) as x
                  ON x.id2 = reporting_urlreport.id
                ORDER BY high DESC, medium DESC, low DESC, url_id ASC
                '''
    # print(sql)
    # Doing this causes some delay. Would we add the calculation without the json conversion (which is 100% anyway)
    # it would take 8 seconds to handle the first few.
    # Would we add json loading via the standard json library it's 16 seconds.
    # Doing it via the faster simplejson, it's 12 seconds.
    # Via Urlrating.objects.raw it's 13 seconds.
    # It's a bit waste to re-load a json string. Without it would be 25% to 50% faster.
    # https://github.com/derek-schaefer/django-json-field
    # https://docs.python.org/3/library/json.html#json.JSONEncoder
    return UrlReport.objects.raw(sql)


def relevant_urls_at_timepoint(queryset, when: datetime):
    # doing this, without the flat list results in about 40% faster execution, most notabily on large organizations
    # if you want to see what's going on, see relevant_urls_at_timepoint
    # removed the IN query to gain some extra speed
    # returned a flat list of pk's, since we don't do anything else with these urls. It's not particulary faster.
    both = queryset.filter(
        # resolvable_in_the_past
        Q(created_on__lte=when, not_resolvable=True, not_resolvable_since__gte=when)
        |
        # alive_in_the_past
        Q(created_on__lte=when, is_dead=True, is_dead_since__gte=when)
        |
        # currently_alive_and_resolvable
        Q(created_on__lte=when, not_resolvable=False, is_dead=False)
    ).filter(
        # relevant_endpoints_at_timepoint

        # Alive then and still alive
        Q(endpoint__discovered_on__lte=when, endpoint__is_dead=False)
        |
        # Alive then
        Q(endpoint__discovered_on__lte=when, endpoint__is_dead=True, endpoint__is_dead_since__gte=when)
    ).values_list("id", flat=True)
    # print(both.query)
    return list(set(both))
