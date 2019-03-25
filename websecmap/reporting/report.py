import logging
from copy import deepcopy
from datetime import datetime
from typing import List

import pytz
from celery import group
from constance import config
from deepdiff import DeepDiff
from django.db.models import Q

from websecmap.celery import app
from websecmap.organizations.models import Organization, Url
from websecmap.reporting.models import OrganizationReport, UrlReport
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)


START_DATE = datetime(year=2016, month=1, day=1, hour=13, minute=37, second=42, tzinfo=pytz.utc)

"""
Warning: Make sure the output of a rebuild has ID's in chronological order.

This code doesn't understand anything else than organizations and urls. All other stuff like the impact on countries,
lists of urls or other constructs you have to derive from the reports made here.
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


@app.task(queue='storage')
def update_report_tasks(url_chunk: List[Url]):
    """
    A small update function that only rebuilds a single url and the organization report for a single day. Using this
    during onboarding, it's possible to show changes much faster than a complete rebuild.

    :param url_chunk: List of urls
    :return:
    """
    tasks = []

    for url in url_chunk:

        organizations = list(url.organization.all())

        # Note that you cannot determine the moment to be "now" as the urls have to be re-reated.
        # the moment to rerate organizations is when the url_ratings has finished.

        tasks.append(recreate_url_reports.si([url]) | create_organization_reports_now.si(organizations))

        # Calculating statistics is _extremely slow_ so we're not doing that in this method to keep the pace.
        # Otherwise you'd have a 1000 statistic rebuilds pending, all doing a marginal job.
        # calculate_vulnerability_statistics.si(1) | calculate_map_data.si(1)

    return group(tasks)


@app.task(queue='storage')
def recreate_url_reports(urls: List):
    """Remove the rating of one url and rebuild anew."""

    # todo: only for allowed organizations...

    for url in urls:
        # Delete the ratings for this url, they are going to be rebuilt
        UrlReport.objects.all().filter(url=url).delete()

        # Creating a timeline and rating it is much faster than doing an individual calculation.
        # Mainly because it gets all data in just a few queries and then builds upon that.
        create_url_report(create_timeline(url), url)


@app.task(queue='storage')
def recreate_organization_reports(organizations: List):
    """Remove organization rating and rebuild a new."""

    # todo: only for allowed organizations...

    for organization in organizations:
        log.info('Adding rating for organization %s', organization)

        # Given yuou're rebuilding, you have to delete all previous ratings:
        OrganizationReport.objects.all().filter(organization=organization).delete()

        # and then rebuild the ratings per moment. This is not really fast.
        # done: reduce the number of significants moments to be weekly in the past, which will safe a lot of time
        # not needed: the rebuild already takes a lot of time, so why bother with that extra hour or so.
        moments, happenings = significant_moments(
            organizations=[organization], reported_scan_types=get_allowed_to_report())
        for moment in moments:
            create_organization_report_on_moment(organization, moment)

        # If there is nothing to show, use a fallback value to display "something" on the map.
        # We cannot add default ratings per organizations per-se, as they would intefear with the timeline.
        # for example: if an organization in 2018 is a merge of organizations in 2017, it will mean that on
        # january first 2018, there would be an empty and perfect rating. That would show up on the map as
        # empty which does not make sense. Therefore we only add a default rating if there is really nothing else.
        if not moments:
            # Make sure the organization has the default rating

            default_organization_rating(organizations=[organization])


constance_cache = {}


def constance_cached_value(key):
    # todo: add this to the constance codebase. Constance is highly inefficient: 1 query per value on each access.
    """
    Tries to minimize access to the database for constance. Every time you want a value, you'll get the latest value.

    That's great but not really needed: it takes 8 roundtrips per url, which is not slow but still slows things down.
    That means about 5000 * 8 database hits per rebuild. = 40.000, which does have an impact.

    This cache holds the value for ten minutes.

    :param key:
    :return:
    """
    now = datetime.now(pytz.utc).timestamp()
    expired = now - 600  # 10 minute cache, 600 seconds. So changes still affect a rebuild.

    if constance_cache.get(key, None):
        if constance_cache[key]['time'] > expired:
            return constance_cache[key]['value']

    # add value to cache, or update cache
    value = getattr(config, key)
    constance_cache[key] = {'value': value, 'time': datetime.now(pytz.utc).timestamp()}
    return value


def significant_moments(organizations: List[Organization] = None, urls: List[Url] = None,
                        reported_scan_types: List[str] = None):
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

    if organizations and urls:
        raise ValueError("Both URL and organization given, please supply one! %s %s" % (organizations, urls))

    if organizations:
        log.debug("Getting all urls from organization: %s" % organizations)
        urls = Url.objects.filter(organization__in=organizations)
    if urls:
        log.debug("Getting all url: %s" % urls)

    if not urls:
        log.info("Could not find urls from organization or url.")
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
    tls_qualys_scans = []
    tls_qualys_scan_dates = []

    generic_scans = EndpointGenericScan.objects.all().filter(type__in=reported_scan_types, endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    generic_scans = latest_rating_per_day_only(generic_scans)
    generic_scan_dates = [x.rating_determined_on for x in generic_scans]
    # this is not faster.
    # generic_scan_dates = list(generic_scans.values_list("rating_determined_on", flat=True))

    # url generic scans
    generic_url_scans = UrlGenericScan.objects.all().filter(type__in=reported_scan_types, url__in=urls).\
        prefetch_related("url")
    generic_url_scans = latest_rating_per_day_only(generic_url_scans)
    generic_url_scan_dates = [x.rating_determined_on for x in generic_url_scans]

    dead_endpoints = Endpoint.objects.all().filter(url__in=urls, is_dead=True)
    dead_scan_dates = [x.is_dead_since for x in dead_endpoints]

    non_resolvable_urls = Url.objects.filter(not_resolvable=True, url__in=urls)
    non_resolvable_dates = [x.not_resolvable_since for x in non_resolvable_urls]

    dead_urls = Url.objects.filter(is_dead=True, url__in=urls)
    dead_url_dates = [x.is_dead_since for x in dead_urls]

    # reduce this to one moment per day only, otherwise there will be a report for every change
    # which is highly inefficient. Using the latest possible time of the day is used.
    moments = tls_qualys_scan_dates + generic_scan_dates + generic_url_scan_dates + non_resolvable_dates + \
        dead_scan_dates + dead_url_dates
    moments = [latest_moment_of_datetime(x) for x in moments]
    moments = sorted(set(moments))

    # If there are no scans at all, just return instead of storing useless junk or make other mistakes
    if not moments:
        return [], {
            'tls_qualys_scans': [],
            'generic_scans': [],
            'generic_url_scans': [],
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
        'tls_qualys_scans': tls_qualys_scans,
        'generic_scans': generic_scans,
        'generic_url_scans': generic_url_scans,
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
        return next((item for item in hash_table if item["hash"] == hash))

    except StopIteration:
        return False


def count_queries(message: str = ""):
    """
    Helps figuring out if django is silently adding more queries / slows things down. Happens when you're
    asking for a property that was not in the original query.

    Note, this stops counting at 9000. See BaseDatabaseWrapper.queries_limit

    :return:
    """
    from django.db import connection
    queries_performed = len(connection.queries)
    if queries_performed > 9000:
        log.debug("Maximum number of queries reached.")

    length_short, length_medium, length_long = 0, 0, 0

    for query in connection.queries:
        if len(query['sql']) <= 100:
            length_short += 1
        if 100 < len(query['sql']) < 300:
            length_medium += 1
        if len(query['sql']) >= 300:
            length_long += 1

    log.debug("# queries: %3s L: %2s, M %2s, S:%2s(%s)" %
              (len(connection.queries), length_long, length_medium, length_short, message))


def show_last_query():
    from django.db import connection

    if not len(connection.queries):
        return

    log.debug(connection.queries[len(connection.queries) - 1])


def show_queries():
    from django.db import connection
    log.debug(connection.queries)


def query_contains_begin():
    """
    A large number of empty begin queries was issues on sqlite during development. This was just as much as the normal
    inserts and saves, which is 60.000 roundtrips. Staring with BEGIN but never finishing the transaction makes no
    sense. WHY? When are the transactions stopped?

    It's embedded in Django's save and delete functions. It always issues a BEGIN statement, even if it's not needed.

    This is the reason:
    https://github.com/django/django/blob/f1d163449396f8bab6c50f4b8b54829d139feda2/django/db/backends/sqlite3/base.py

    From the code:
    Start a transaction explicitly in autocommit mode.
    Staying in autocommit mode works around a bug of sqlite3 that breaks savepoints when autocommit is disabled.

    And more meaningful comments here:
    https://github.com/django/django/blob/717ee63e5615a6c3a018351a07028513f9b01f0b/django/db/backends/base/base.py

    OK, we're rolling with it. Thnx open source docs and django devs for being clear.
    :return:
    """
    from django.db import connection

    for query in connection.queries:
        if query['sql'] == 'BEGIN':
            log.error('BEGIN')


def hash_scan_per_day_and_type(scan):

    # hopefully it doesn't run extra queries?
    if scan.type in URL_SCAN_TYPES:
        pk = scan.url.pk
    else:
        pk = scan.endpoint.pk

    return "%s%s%s" % (pk, scan.type, scan.rating_determined_on.date())


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
        moment_date = moment.date()
        timeline[moment_date] = {}
        timeline[moment_date]["endpoints"] = []
        timeline[moment_date]['scans'] = []   # todo: should be named endpoint_scans
        timeline[moment_date]['url_scans'] = []
        timeline[moment_date]["dead_endpoints"] = []
        timeline[moment_date]["urls"] = []

    # sometimes there have been scans on dead endpoints. This is a problem in the database.
    # this code is correct with retrieving those endpoints again.
    # we could save a list of dead endpoints, but the catch is that an endpoint can start living
    # again over time. The scans with only dead endpoints should not be made.

    for scan in happenings['generic_scans']:
        some_day = scan.rating_determined_on.date()

        # can we create this set in an easier way?
        if "generic_scan" not in timeline[some_day]:
            timeline[some_day]["generic_scan"] = {'scans': [], 'endpoints': []}

        # timeline[some_day]["generic_scan"]["scanned"] = True  # do we ever check on this? Seems not.
        timeline[some_day]["generic_scan"]['scans'].append(scan)
        timeline[some_day]["generic_scan"]["endpoints"].append(scan.endpoint)
        timeline[some_day]["endpoints"].append(scan.endpoint)
        timeline[some_day]['scans'].append(scan)  # todo: should be named endpoint_scans

    for scan in happenings['generic_url_scans']:
        some_day = scan.rating_determined_on.date()

        # can we create this set in an easier way?
        if "generic_url_scan" not in timeline[some_day]:
            timeline[some_day]["generic_url_scan"] = {'scans': [], 'urls': []}

        # timeline[some_day]["generic_scan"]["scanned"] = True  # do we ever check on this? Seems not.
        timeline[some_day]["generic_url_scan"]['scans'].append(scan)
        timeline[some_day]["generic_url_scan"]["urls"].append(scan.url)
        timeline[some_day]["urls"].append(scan.url)
        timeline[some_day]['url_scans'].append(scan)

    for scan in happenings['tls_qualys_scans']:
        some_day = scan.rating_determined_on.date()

        # can we create this set in an easier way?
        if "tls_qualys" not in timeline[some_day]:
            timeline[some_day]["tls_qualys"] = {'scans': [], 'endpoints': []}

        timeline[some_day]["tls_qualys"]['scans'].append(scan)
        timeline[some_day]["tls_qualys"]["endpoints"].append(scan.endpoint)
        timeline[some_day]["endpoints"].append(scan.endpoint)
        timeline[some_day]['scans'].append(scan)  # todo: should be named endpoint_scans

    # Any endpoint from this point on should be removed. If the url becomes alive again, add it again, so you can
    # see there are gaps in using the url over time. Which is more truthful.
    for moment in [not_resolvable_url.not_resolvable_since for not_resolvable_url in happenings['non_resolvable_urls']]:
        timeline[moment.date()]["url_not_resolvable"] = True

    for moment in [dead_url.is_dead_since for dead_url in happenings['dead_urls']]:
        timeline[moment.date()]["url_is_dead"] = True

    for endpoint in happenings['dead_endpoints']:
        some_day = endpoint.is_dead_since.date()
        timeline[some_day]["dead"] = True
        if endpoint not in timeline[some_day]["dead_endpoints"]:
            timeline[some_day]["dead_endpoints"].append(endpoint)

    # unique endpoints only
    for moment in moments:
        some_day = moment.date()
        timeline[some_day]["endpoints"] = list(set(timeline[some_day]["endpoints"]))

    # try to return dates in chronological order
    return timeline


def latest_moment_of_datetime(datetime_: datetime):
    return datetime_.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)


def create_url_report(timeline, url: Url):
    log.info("Rebuilding ratings for url %s on %s moments" % (url, len(timeline)))
    previous_endpoint_ratings = {}
    previous_url_ratings = {}
    previous_endpoints = []
    url_was_once_rated = False

    # work on a sorted timeline as otherwise this code is non-deterministic!
    for moment in sorted(timeline):
        total_high, total_medium, total_low = 0, 0, 0
        explained_total_high, explained_total_medium, explained_total_low = 0, 0, 0
        given_ratings = {}

        if ('url_not_resolvable' in timeline[moment] or 'url_is_dead' in timeline[moment]) \
                and url_was_once_rated:
            log.debug('Url became non-resolvable or dead. Adding an empty rating to lower the score of'
                      'this domain if it had a score. It has been cleaned up. (hooray)')
            # this is the end for the domain.
            default_calculation = {
                "url": {
                    "url": url.url,
                    "ratings": [],
                    "endpoints": [],

                    "total_issues:": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    'ok': 0,
                    "total_endpoints": 0,
                    "high_endpoints": 0,
                    "medium_endpoints": 0,
                    "low_endpoints": 0,
                    "ok_endpoints": 0,
                    "total_url_issues": 0,
                    "url_issues_high": 0,
                    "url_issues_medium": 0,
                    "url_issues_low": 0,
                    "url_ok": 0,
                    "total_endpoint_issues": 0,
                    "endpoint_issues_high": 0,
                    "endpoint_issues_medium": 0,
                    "endpoint_issues_low": 0,
                    "endpoint_ok": 0,

                    "explained_total_issues:": 0,
                    "explained_high": 0,
                    "explained_medium": 0,
                    "explained_low": 0,
                    "explained_total_endpoints": 0,
                    "explained_high_endpoints": 0,
                    "explained_medium_endpoints": 0,
                    "explained_low_endpoints": 0,
                    "explained_total_url_issues": 0,
                    "explained_url_issues_high": 0,
                    "explained_url_issues_medium": 0,
                    "explained_url_issues_low": 0,
                    "explained_total_endpoint_issues": 0,
                    "explained_endpoint_issues_high": 0,
                    "explained_endpoint_issues_medium": 0,
                    "explained_endpoint_issues_low": 0,
                }
            }

            save_url_report(url, moment, 0, 0, 0, default_calculation, total_issues=0, total_endpoints=0,
                            high_endpoints=0, medium_endpoints=0, low_endpoints=0)
            return

        # reverse the relation: so we know all ratings per endpoint.
        # It is not really relevant what endpoints _really_ exist.
        endpoint_scans = {}
        for scan in timeline[moment]['scans']:
            endpoint_scans[scan.endpoint.id] = []

        for scan in timeline[moment]['scans']:
            endpoint_scans[scan.endpoint.id].append(scan)

        # create the report for this moment
        endpoint_reports = []

        # also include all endpoints from the past time, which we do until the endpoints are dead.
        relevant_endpoints = set(timeline[moment]["endpoints"] + previous_endpoints)

        # remove dead endpoints
        # we don't need to remove the previous ratings, unless we want to save memory (Nah :))
        if "dead_endpoints" in timeline[moment]:
            for dead_endpoint in timeline[moment]["dead_endpoints"]:
                # endpoints can die this moment,
                # note that this removes only once. if the endpoint was rated twice with the same rating, the older one
                # is still in there. Therefore it's not an IF but a WHILE statement.
                while dead_endpoint in relevant_endpoints:
                    relevant_endpoints.remove(dead_endpoint)
                # remove the endpoint from the past
                while dead_endpoint in previous_endpoints:
                    previous_endpoints.remove(dead_endpoint)

        total_endpoints, high_endpoints, medium_endpoints, low_endpoints, ok_endpoints = 0, 0, 0, 0, 0
        explained_high_endpoints, explained_medium_endpoints, explained_low_endpoints = 0, 0, 0

        # Some sums that will be saved as stats:
        endpoint_issues_high, endpoint_issues_medium, endpoint_issues_low = 0, 0, 0
        explained_endpoint_issues_high, explained_endpoint_issues_medium, explained_endpoint_issues_low = 0, 0, 0
        for endpoint in relevant_endpoints:
            # All endpoints of all time are iterated. The dead endpoints etc should be filtered out above.
            total_endpoints += 1
            url_was_once_rated = True

            calculations = []
            these_endpoint_scans = {}
            if endpoint.id in endpoint_scans:
                for scan in endpoint_scans[endpoint.id]:
                    if scan.type in ENDPOINT_SCAN_TYPES:
                        these_endpoint_scans[scan.type] = scan

            # enrich the ratings with previous ratings, without overwriting them.
            for endpoint_scan_type in ENDPOINT_SCAN_TYPES:
                if endpoint_scan_type not in these_endpoint_scans:
                    if endpoint.id in previous_endpoint_ratings:
                        if endpoint_scan_type in previous_endpoint_ratings[endpoint.id]:
                            these_endpoint_scans[endpoint_scan_type] = \
                                previous_endpoint_ratings[endpoint.id][endpoint_scan_type]

            # propagate the ratings to the next iteration.
            previous_endpoint_ratings[endpoint.id] = {}
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
            label = str(moment) + str(endpoint.is_ipv6()) + str(endpoint.port)
            if label not in given_ratings:
                given_ratings[label] = []

            endpoint_high, endpoint_medium, endpoint_low = 0, 0, 0
            explained_endpoint_high, explained_endpoint_medium, explained_endpoint_low = 0, 0, 0
            for endpoint_scan_type in ENDPOINT_SCAN_TYPES:
                if endpoint_scan_type in these_endpoint_scans:
                    if endpoint_scan_type not in given_ratings[label]:
                        calculation = get_severity(these_endpoint_scans[endpoint_scan_type])
                        if calculation:
                            calculations.append(calculation)
                            if these_endpoint_scans[endpoint_scan_type].comply_or_explain_is_explained:
                                explained_endpoint_high += calculation["high"]
                                explained_endpoint_issues_high += calculation["high"]
                                explained_endpoint_medium += calculation["medium"]
                                explained_endpoint_issues_medium += calculation["medium"]
                                explained_endpoint_low += calculation["low"]
                                explained_endpoint_issues_low += calculation["low"]
                                explained_total_high += calculation["high"]
                                explained_total_medium += calculation["medium"]
                                explained_total_low += calculation["low"]
                            else:
                                endpoint_high += calculation["high"]
                                endpoint_issues_high += calculation["high"]
                                endpoint_medium += calculation["medium"]
                                endpoint_issues_medium += calculation["medium"]
                                endpoint_low += calculation["low"]
                                endpoint_issues_low += calculation["low"]
                                total_high += calculation["high"]
                                total_medium += calculation["medium"]
                                total_low += calculation["low"]

                        given_ratings[label].append(endpoint_scan_type)
                    else:
                        calculations.append({
                            "type": endpoint_scan_type,
                            "explanation": "Repeated finding. Probably because this url changed IP adresses or has "
                                           "multiple IP adresses (common for failover / load-balancing).",
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                            "ok": 0,
                            "since": these_endpoint_scans[endpoint_scan_type].rating_determined_on.isoformat(),
                            "last_scan": these_endpoint_scans[endpoint_scan_type].last_scan_moment.isoformat(),

                            # With this empty calculation, make sure all standard fields are available.
                            'is_explained': False,
                            'comply_or_explain_explanation': '',
                            'comply_or_explain_explained_on': '',
                            'comply_or_explain_explanation_valid_until': '',
                            'comply_or_explain_valid_at_time_of_report': False
                        })

            endpoint_ok = 0 if endpoint_high or endpoint_medium or endpoint_low else 1

            # give an idea how many endpoint issues there are compared to the total # of endpoints
            if endpoint_high:
                high_endpoints += 1
            if endpoint_medium:
                medium_endpoints += 1
            if endpoint_low:
                low_endpoints += 1
            if endpoint_ok:
                ok_endpoints += 1

            if explained_endpoint_high:
                explained_high_endpoints += 1
            if explained_endpoint_medium:
                explained_medium_endpoints += 1
            if explained_endpoint_low:
                explained_low_endpoints += 1

            # Readibility is important: it's ordered from the worst to least points.
            calculations = sorted(calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

            endpoint_reports.append({
                "id": endpoint.pk,
                "concat": "%s/%s IPv%s" % (endpoint.protocol, endpoint.port, endpoint.ip_version),
                "ip": endpoint.ip_version,
                "ip_version": endpoint.ip_version,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "v4": endpoint.is_ipv4(),
                "high": endpoint_high,
                "medium": endpoint_medium,
                "low": endpoint_low,
                "ok": endpoint_ok,
                "explained_high": explained_endpoint_high,
                "explained_medium":  explained_endpoint_medium,
                "explained_low":  explained_endpoint_low,
                "ratings": calculations
            })

        previous_endpoints += relevant_endpoints

        # Add url generic scans, using the same logic as endpoints.
        # - It reuses ratings from the previous moment, but if there are new ratings for a specific scan type only the
        # rating for this specific scan type is overwritten.
        # - Dead and not resolvable urls have been checked above, which helps.
        url_scans = {}
        for scan in timeline[moment]['url_scans']:
            url_scans[scan.url.id] = []

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
            if url_scan_type not in these_url_scans:
                if url.id in previous_url_ratings:
                    if url_scan_type in previous_url_ratings[url.id]:
                        these_url_scans[url_scan_type] = \
                            previous_url_ratings[url.id][url_scan_type]

        # propagate the ratings to the next iteration.
        previous_url_ratings[url.id] = {}
        previous_url_ratings[url.id] = these_url_scans

        url_issues_high, url_issues_medium, url_issues_low = 0, 0, 0
        explained_url_issues_high, explained_url_issues_medium, explained_url_issues_low = 0, 0, 0
        for url_scan_type in url_scan_types:
            if url_scan_type in these_url_scans:
                calculation = get_severity(these_url_scans[url_scan_type])
                if calculation:
                    url_calculations.append(calculation)
                    if these_url_scans[url_scan_type].comply_or_explain_is_explained:
                        explained_url_issues_high += calculation["high"]
                        explained_total_high += calculation["high"]
                        explained_total_medium += calculation["medium"]
                        explained_url_issues_medium += calculation["medium"]
                        explained_total_low += calculation["low"]
                        explained_url_issues_low += calculation["low"]
                    else:
                        url_issues_high += calculation["high"]
                        total_high += calculation["high"]
                        total_medium += calculation["medium"]
                        url_issues_medium += calculation["medium"]
                        total_low += calculation["low"]
                        url_issues_low += calculation["low"]

        # prevent empty ratings cluttering the database and skewing the stats.
        # todo: only do this if there never was a urlrating before this.
        if not endpoint_reports and not url_was_once_rated and not url_calculations:
            continue

        url_issues_ok = 0 if url_issues_high or url_issues_medium or url_issues_low else 1

        total_url_issues = url_issues_high + url_issues_medium + url_issues_low
        explained_total_url_issues = explained_url_issues_high + explained_url_issues_medium + explained_url_issues_low
        total_endpoint_issues = endpoint_issues_high + endpoint_issues_medium + endpoint_issues_low
        explained_total_endpoint_issues = \
            explained_endpoint_issues_high + explained_endpoint_issues_medium + explained_endpoint_issues_low

        url_and_endpoints_ok = 0 if total_endpoint_issues or total_url_issues else 1
        sorted_url_reports = sorted(url_calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

        sorted_endpoints_reports = sorted(
            endpoint_reports, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

        total_issues = total_high + total_medium + total_low
        explained_total_issues = explained_total_high + explained_total_medium + explained_total_low
        calculation = {
            "url": url.url,
            "ratings": sorted_url_reports,
            "endpoints": sorted_endpoints_reports,

            "total_issues": total_issues,
            "high": total_high,
            "medium": total_medium,
            "low": total_low,
            "ok": url_and_endpoints_ok,
            "total_endpoints": total_endpoints,
            "high_endpoints": high_endpoints,
            "medium_endpoints": medium_endpoints,
            "low_endpoints": low_endpoints,
            "ok_endpoints": ok_endpoints,
            "total_url_issues": total_url_issues,
            "url_issues_high": url_issues_high,
            "url_issues_medium": url_issues_medium,
            "url_issues_low": url_issues_low,
            "url_ok": url_issues_ok,
            "total_endpoint_issues": total_endpoint_issues,
            "endpoint_issues_high": endpoint_issues_high,
            "endpoint_issues_medium": endpoint_issues_medium,
            "endpoint_issues_low": endpoint_issues_low,

            "explained_total_issues": explained_total_issues,
            "explained_high": explained_total_high,
            "explained_medium": explained_total_medium,
            "explained_low": explained_total_low,
            # The number of endpoints doesn't change if issues are explained,
            # just like the number of urls doesn't change.
            # "explained_total_endpoints": explained_total_endpoints,
            "explained_high_endpoints": explained_high_endpoints,
            "explained_medium_endpoints": explained_medium_endpoints,
            "explained_low_endpoints": explained_low_endpoints,
            "explained_total_url_issues": explained_total_url_issues,
            "explained_url_issues_high": explained_url_issues_high,
            "explained_url_issues_medium": explained_url_issues_medium,
            "explained_url_issues_low": explained_url_issues_low,
            "explained_total_endpoint_issues": explained_total_endpoint_issues,
            "explained_endpoint_issues_high": explained_endpoint_issues_high,
            "explained_endpoint_issues_medium": explained_endpoint_issues_medium,
            "explained_endpoint_issues_low": explained_endpoint_issues_low,
        }

        log.debug("On %s %s has %s endpoints and %s high, %s medium and %s low vulnerabilities" %
                  (moment, url, len(sorted_endpoints_reports), total_high, total_medium, total_low))

        save_url_report(url, moment, total_high, total_medium, total_low, calculation,
                        total_issues=total_issues, total_endpoints=total_endpoints, high_endpoints=high_endpoints,
                        medium_endpoints=medium_endpoints, low_endpoints=low_endpoints,
                        total_url_issues=total_url_issues, total_endpoint_issues=total_endpoint_issues,
                        url_issues_high=url_issues_high, url_issues_medium=url_issues_medium,
                        url_issues_low=url_issues_low, endpoint_issues_high=endpoint_issues_high,
                        endpoint_issues_medium=endpoint_issues_medium, endpoint_issues_low=endpoint_issues_low,
                        explained_high=explained_total_high, explained_medium=explained_total_medium,
                        explained_low=explained_total_low,
                        explained_total_issues=explained_total_issues,
                        explained_high_endpoints=explained_high_endpoints,
                        explained_medium_endpoints=explained_medium_endpoints,
                        explained_low_endpoints=explained_low_endpoints,
                        explained_total_url_issues=explained_total_url_issues,
                        explained_total_endpoint_issues=explained_total_endpoint_issues,
                        explained_url_issues_high=explained_url_issues_high,
                        explained_url_issues_medium=explained_url_issues_medium,
                        explained_url_issues_low=explained_url_issues_low,
                        explained_endpoint_issues_high=explained_endpoint_issues_high,
                        explained_endpoint_issues_medium=explained_endpoint_issues_medium,
                        explained_endpoint_issues_low=explained_endpoint_issues_low,
                        ok=url_and_endpoints_ok, ok_endpoints=ok_endpoints, url_ok=url_issues_ok,
                        )


def save_url_report(url: Url, date: datetime, high: int, medium: int, low: int, calculation,
                    total_issues: int = 0, total_endpoints: int = 0,
                    high_endpoints: int = 0, medium_endpoints: int = 0, low_endpoints: int = 0,
                    total_url_issues: int = 0, total_endpoint_issues: int = 0,
                    url_issues_high: int = 0, url_issues_medium: int = 0, url_issues_low: int = 0,
                    endpoint_issues_high: int = 0, endpoint_issues_medium: int = 0, endpoint_issues_low: int = 0,

                    explained_high: int = 0, explained_medium: int = 0, explained_low: int = 0,
                    explained_total_issues: int = 0, explained_high_endpoints: int = 0,
                    explained_medium_endpoints: int = 0, explained_low_endpoints: int = 0,
                    explained_total_url_issues: int = 0, explained_total_endpoint_issues: int = 0,
                    explained_url_issues_high: int = 0, explained_url_issues_medium: int = 0,
                    explained_url_issues_low: int = 0, explained_endpoint_issues_high: int = 0,
                    explained_endpoint_issues_medium: int = 0, explained_endpoint_issues_low: int = 0,
                    ok: int = 0, ok_endpoints: int = 0, url_ok: int = 0, endpoint_ok: int = 0
                    ):
    u = UrlReport()
    u.url = url

    # save it as NOW if it's done today, else on the last moment on the same day.
    # So the url ratings immediately are shown, even if the day is not over.

    if date == datetime.now().date():
        u.when = datetime.now(pytz.utc)
    else:
        u.when = datetime(year=date.year, month=date.month, day=date.day,
                          hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)

    u.calculation = calculation
    u.total_endpoints = total_endpoints

    u.high = high
    u.medium = medium
    u.low = low
    u.ok = ok

    u.total_issues = total_issues
    u.high_endpoints = high_endpoints
    u.medium_endpoints = medium_endpoints
    u.low_endpoints = low_endpoints
    u.ok_endpoints = ok_endpoints
    u.total_url_issues = total_url_issues
    u.total_endpoint_issues = total_endpoint_issues
    u.url_issues_high = url_issues_high
    u.url_issues_medium = url_issues_medium
    u.url_issues_low = url_issues_low
    # probably the same as OK, as you can only be OK once.
    u.url_ok = url_ok
    u.endpoint_issues_high = endpoint_issues_high
    u.endpoint_issues_medium = endpoint_issues_medium
    u.endpoint_issues_low = endpoint_issues_low
    u.endpoint_ok = endpoint_ok

    u.explained_high = explained_high
    u.explained_medium = explained_medium
    u.explained_low = explained_low
    u.explained_total_issues = explained_total_issues
    u.explained_high_endpoints = explained_high_endpoints
    u.explained_medium_endpoints = explained_medium_endpoints
    u.explained_low_endpoints = explained_low_endpoints
    u.explained_total_url_issues = explained_total_url_issues
    u.explained_total_endpoint_issues = explained_total_endpoint_issues
    u.explained_url_issues_high = explained_url_issues_high
    u.explained_url_issues_medium = explained_url_issues_medium
    u.explained_url_issues_low = explained_url_issues_low
    u.explained_endpoint_issues_high = explained_endpoint_issues_high
    u.explained_endpoint_issues_medium = explained_endpoint_issues_medium
    u.explained_endpoint_issues_low = explained_endpoint_issues_low
    u.save()


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

        if 'tls_qualys' in timeline[moment]:
            message += "|  |- tls_qualys" + newline
            for item in timeline[moment]['tls_qualys']['endpoints']:
                message += "|  |  |- Endpoint %s" % item + newline
            for item in timeline[moment]['tls_qualys']['scans']:
                calculation = get_severity(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'generic_url_scan' in timeline[moment]:
            message += "|  |- url generic_scan" + newline
            for item in timeline[moment]['generic_url_scan']['scans']:
                calculation = get_severity(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'generic_scan' in timeline[moment]:
            message += "|  |- endpoint generic_scan" + newline
            for item in timeline[moment]['generic_scan']['scans']:
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


@app.task(queue='storage')
def create_organization_reports_now(organizations: List[Organization]):

    for organization in organizations:
        now = datetime.now(pytz.utc)
        create_organization_report_on_moment(organization, now)


# also callable as admin action
# this is 100% based on url ratings, just an aggregate of the last status.
# make sure the URL ratings are up to date, they will check endpoints and such.
def create_organization_report_on_moment(organization: Organization, when: datetime = None):
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    log.info("Creating report for %s on %s" % (organization, when, ))

    # if there already is an organization rating on this moment, skip it. You should have deleted it first.
    # this is probably a lot quicker than calculating the score and then deepdiffing it.
    # using this check we can also ditch deepdiff, because ratings on the same day are always the same.
    # todo: we should be able to continue on a certain day.
    if OrganizationReport.objects.all().filter(organization=organization, when=when).exists():
        log.info("Rating already exists for %s on %s. Not overwriting." % (organization, when))

    # Done: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_organization(organization=organization, when=when)

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)
    scores = aggegrate_url_rating_scores(all_url_ratings)

    # Still do deepdiff to prevent double reports.
    try:
        last = OrganizationReport.objects.filter(
            organization=organization, when__lte=when).latest('when')
    except OrganizationReport.DoesNotExist:
        log.debug("Could not find the last organization rating, creating a dummy one.")
        last = OrganizationReport()  # create an empty one

    scores['name'] = organization.name
    calculation = {"organization": scores}

    # this is 10% faster without deepdiff, the major pain is elsewhere.
    if DeepDiff(last.calculation, calculation, ignore_order=True, report_repetition=True):
        log.info("The calculation for %s on %s has changed, so we're saving this rating." % (organization, when))

        # remove urls and name from scores object, so it can be used as initialization parameters (saves lines)
        # this is by reference, meaning that the calculation will be affected if we don't work on a clone.
        init_scores = deepcopy(scores)
        del(init_scores['name'])
        del(init_scores['urls'])

        organizationrating = OrganizationReport(**init_scores)
        organizationrating.organization = organization
        organizationrating.when = when
        organizationrating.calculation = calculation

        organizationrating.save()
        log.info("Saved report for %s on %s." % (organization, when))
    else:
        # This happens because some urls are dead etc: our filtering already removes this from the relevant information
        # at this point in time. But since it's still a significant moment, it will just show that nothing has changed.
        log.warning("The calculation for %s on %s is the same as the previous one. Not saving." % (organization, when))


def aggegrate_url_rating_scores(url_ratings: List):
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

        scores['high'] += urlrating.high
        scores['medium'] += urlrating.medium
        scores['low'] += urlrating.low
        scores['ok_urls'] += urlrating.url_ok

        scores['total_endpoints'] += urlrating.total_endpoints
        scores['high_endpoints'] += urlrating.high_endpoints
        scores['medium_endpoints'] += urlrating.medium_endpoints
        scores['low_endpoints'] += urlrating.low_endpoints
        scores['ok_endpoints'] += urlrating.ok_endpoints

        scores['total_url_issues'] += urlrating.total_url_issues
        scores['total_endpoint_issues'] += urlrating.total_endpoint_issues
        scores['url_issues_high'] += urlrating.url_issues_high
        scores['url_issues_medium'] += urlrating.url_issues_medium
        scores['url_issues_low'] += urlrating.url_issues_low
        scores['endpoint_issues_high'] += urlrating.endpoint_issues_high
        scores['endpoint_issues_medium'] += urlrating.endpoint_issues_medium
        scores['endpoint_issues_low'] += urlrating.endpoint_issues_low

        scores['explained_total_endpoint_issues'] += urlrating.explained_total_endpoint_issues
        scores['explained_endpoint_issues_high'] += urlrating.explained_endpoint_issues_high
        scores['explained_endpoint_issues_medium'] += urlrating.explained_endpoint_issues_medium
        scores['explained_endpoint_issues_low'] += urlrating.explained_endpoint_issues_low
        scores['explained_total_url_issues'] += urlrating.explained_total_url_issues
        scores['explained_url_issues_high'] += urlrating.explained_url_issues_high
        scores['explained_url_issues_medium'] += urlrating.explained_url_issues_medium
        scores['explained_url_issues_low'] += urlrating.explained_url_issues_low
        scores['explained_high_urls'] += 1 if urlrating.explained_url_issues_high else 0
        scores['explained_medium_urls'] += 1 if urlrating.explained_url_issues_medium else 0
        scores['explained_low_urls'] += 1 if urlrating.explained_url_issues_low else 0
        scores['explained_high_endpoints'] += urlrating.explained_high_endpoints
        scores['explained_medium_endpoints'] += urlrating.explained_medium_endpoints
        scores['explained_low_endpoints'] += urlrating.explained_low_endpoints
        scores['explained_high'] += urlrating.explained_high
        scores['explained_medium'] += urlrating.explained_medium
        scores['explained_low'] += urlrating.explained_low

        scores['total_urls'] += 1

        # url can only be in one category (otherwise there are urls in multiple categories which makes it
        # hard to display)
        if urlrating.high_endpoints:
            scores['high_urls'] += 1
        elif urlrating.medium_endpoints:
            scores['medium_urls'] += 1
        elif urlrating.low_endpoints:
            scores['low_urls'] += 1

        scores['urls'].append(urlrating.calculation)

    scores['total_issues'] = scores['high'] + scores['medium'] + scores['low']

    # the score cannot be OK if there are no urls.
    scores['ok'] = 0 if scores['total_issues'] else 1 if scores['total_urls'] else 0

    return scores


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
                  WHERE `when` <= '%s' AND url_id IN (''' % (when, ) + ','.join(map(str, urls)) + ''')
                  GROUP BY url_id) as x
                  ON x.id2 = reporting_urlreport.id
                ORDER BY `high` DESC, `medium` DESC, `low` DESC, `url_id` ASC
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


def relevant_urls_at_timepoint_organization(organization: Organization, when: datetime):
    # doing this, without the flat list results in about 40% faster execution, most notabily on large organizations
    # if you want to see what's going on, see relevant_urls_at_timepoint
    # removed the IN query to gain some extra speed
    # returned a flat list of pk's, since we don't do anything else with these urls. It's not particulary faster.
    queryset = Url.objects.filter(organization=organization)
    return relevant_urls_at_timepoint(queryset, when)


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


@app.task(queue='storage')
def default_organization_rating(organizations: List[Organization]):
    """
    Generate default ratings so all organizations are on the map (as being grey). This prevents
    empty spots / holes.
    :return:
    """

    if not organizations:
        organizations = Organization.objects.all()

    for organization in organizations:
        log.info("Giving organization a default rating: %s" % organization)

        when = organization.created_on if organization.created_on else START_DATE

        r = OrganizationReport()
        r.when = when
        r.organization = organization
        r.calculation = {
            "organization": {
                "name": organization.name,
                "high": 0,
                "medium": 0,
                "low": 0,
                "ok": 0,
                "urls": []
            }
        }
        r.save()
