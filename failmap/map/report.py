import logging
from datetime import datetime, timedelta
from typing import List

import pytz
from celery import group
from constance import config
from deepdiff import DeepDiff
from django.db.models import Q

from failmap.map.views import get_map_data
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan, UrlGenericScan
from failmap.scanners.scanner.scanner import q_configurations_to_report

from ..celery import Task, app
from .calculate import get_calculation
from .models import (Configuration, MapDataCache, OrganizationRating, UrlRating,
                     VulnerabilityStatistic)

log = logging.getLogger(__package__)

from failmap.scanners.types import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

FAILMAP_STARTED = datetime(year=2016, month=1, day=1, hour=13, minute=37, second=42, tzinfo=pytz.utc)

"""
Warning: Make sure the output of a rebuild has ID's in chronological order.
"""


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """
    Compose taskset to rebuild specified organizations/urls.
    """

    if endpoints_filter:
        raise NotImplementedError('This scanner does not work on a endpoint level.')

    log.info("Organization filter: %s" % organizations_filter)
    log.info("Url filter: %s" % urls_filter)

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(q_configurations_to_report('organization'), **organizations_filter)

    log.debug("Organizations: %s" % len(organizations))

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []

    for organization in organizations:
        urls = Url.objects.filter(q_configurations_to_report(), organization=organization, **urls_filter)
        if not urls:
            continue

        # make sure default organization rating is in place
        tasks.append(rebuild_url_ratings.si(urls)
                     | rate_organizations_now.si([organization]))

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s" % organizations_filter)
        log.debug("Url filter: %s" % urls_filter)
        log.debug("urls to display: %s" % q_configurations_to_report())
        log.debug("organizatins to display: %s" % q_configurations_to_report('organization'))
        return group()

    # when trying to report on a specific url or organization (so not everything) also don't rebuild all caches
    # from the past. This saves a lot of rebuild time, making results visible in a "fixing state" and the entire rebuild
    # will happen at a scheduled interval to make sure the rest is up to date.
    if organizations_filter or urls_filter:
        days = 2
    else:
        # no, you always want to have a pretty quick update. If you want to revise the entire dataset, you might
        # have adjusted the value of the ratings somewhere. Then that would be a special operation to recalculate
        # the entire database. So this can just be two days as well.
        days = 2

    log.debug("Number of tasks: %s" % len(tasks))

    # finally, rebuild the graphs (which can mis-matchi a bit if the last reports aren't in yet. Will have to do for now
    # mainly as we're trying to get away from canvas and it's buggyness.
    tasks.append(calculate_vulnerability_statistics.si(days))

    # also try to speed up the map view
    tasks.append(calculate_map_data.si(days))

    task = group(tasks)

    return task


@app.task(queue='storage')
def update_report_tasks(url: Url):
    """
    A small update function that only rebuilds a single url and the organization report for a single day. Using this
    during onboarding, it's possible to show changes much faster than a complete rebuild.

    :param url:
    :return:
    """
    tasks = []

    organizations = list(url.organization.all())

    # Note that you cannot determine the moment to be "now" as the urls have to be re-reated.
    # the moment to rerate organizations is when the url_ratings has finished.

    tasks.append(rebuild_url_ratings.si([url]) | rate_organizations_now.si(organizations))

    # Calculating statistics is _extremely slow_ so we're not doing that in this method to keep the pace.
    # Otherwise you'd have a 1000 statistic rebuilds pending, all doing a marginal job.
    # calculate_vulnerability_statistics.si(1) | calculate_map_data.si(1)

    return group(tasks)


@app.task(queue='storage')
def rebuild_url_ratings(urls: List):
    """Remove the rating of one url and rebuild anew."""

    for url in urls:
        # Delete the ratings for this url, they are going to be rebuilt
        UrlRating.objects.all().filter(url=url).delete()

        # Creating a timeline and rating it is much faster than doing an individual calculation.
        # Mainly because it gets all data in just a few queries and then builds upon that.
        rate_timeline(create_timeline(url), url)


@app.task(queue='storage')
def rebuild_organization_ratings(organizations: List):
    """Remove organization rating and rebuild anew."""

    for organization in organizations:
        log.info('Adding rating for organization %s', organization)

        # Given yuou're rebuilding, you have to delete all previous ratings:
        OrganizationRating.objects.all().filter(organization=organization).delete()

        # Make sure the organization has the default rating
        default_organization_rating(organizations=[organization])

        # and then rebuild the ratings per moment. This is not really fast.
        # done: reduce the number of significants moments to be weekly in the past, which will safe a lot of time
        # not needed: the rebuild already takes a lot of time, so why bother with that extra hour or so.
        moments, happenings = significant_moments(organizations=[organization])
        for moment in moments:
            rate_organization_on_moment(organization, moment)


constance_cache = {}


def constance_cached_value(key):
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


def significant_moments(organizations: List[Organization] = None, urls: List[Url] = None):
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

    allowed_to_report = []
    if constance_cached_value('REPORT_INCLUDE_HTTP_MISSING_TLS'):
        allowed_to_report.append("plain_https")
    if constance_cached_value('REPORT_INCLUDE_HTTP_HEADERS_HSTS'):
        allowed_to_report.append("Strict-Transport-Security")
    if constance_cached_value('REPORT_INCLUDE_HTTP_HEADERS_XFO'):
        allowed_to_report.append("X-Frame-Options")
    if constance_cached_value('REPORT_INCLUDE_HTTP_HEADERS_X_XSS'):
        allowed_to_report.append("X-XSS-Protection")
    if constance_cached_value('REPORT_INCLUDE_HTTP_HEADERS_X_CONTENT'):
        allowed_to_report.append("X-Content-Type-Options")
    if constance_cached_value('REPORT_INCLUDE_DNS_DNSSEC'):
        allowed_to_report.append("DNSSEC")
    if constance_cached_value('REPORT_INCLUDE_FTP'):
        allowed_to_report.append("ftp")
    if constance_cached_value('REPORT_INCLUDE_HTTP_TLS_QUALYS'):
        allowed_to_report.append("tls_qualys_certificate_trusted")
        allowed_to_report.append("tls_qualys_encryption_quality")

    generic_scans = EndpointGenericScan.objects.all().filter(type__in=allowed_to_report, endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    generic_scans = latest_rating_per_day_only(generic_scans)
    generic_scan_dates = [x.rating_determined_on for x in generic_scans]
    # this is not faster.
    # generic_scan_dates = list(generic_scans.values_list("rating_determined_on", flat=True))

    # url generic scans
    generic_url_scans = UrlGenericScan.objects.all().filter(type__in=allowed_to_report, url__in=urls).\
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
    moments, happenings = significant_moments(urls=[url])

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


def rate_timeline(timeline, url: Url):
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
                    "total_endpoints": 0,
                    "high_endpoints": 0,
                    "medium_endpoints": 0,
                    "low_endpoints": 0,
                    "total_url_issues": 0,
                    "url_issues_high": 0,
                    "url_issues_medium": 0,
                    "url_issues_low": 0,
                    "total_endpoint_issues": 0,
                    "endpoint_issues_high": 0,
                    "endpoint_issues_medium": 0,
                    "endpoint_issues_low": 0,

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

            save_url_rating(url, moment, 0, 0, 0, default_calculation, total_issues=0, total_endpoints=0,
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

        total_endpoints, high_endpoints, medium_endpoints, low_endpoints = 0, 0, 0, 0
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
                        calculation = get_calculation(these_endpoint_scans[endpoint_scan_type])
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
                            "since": these_endpoint_scans[endpoint_scan_type].rating_determined_on.isoformat(),
                            "last_scan": these_endpoint_scans[endpoint_scan_type].last_scan_moment.isoformat(),

                            # With this empty calculation, make sure all standard fields are available.
                            'is_explained': False,
                            'comply_or_explain_explanation': '',
                            'comply_or_explain_explained_on': '',
                            'comply_or_explain_explanation_valid_until': '',
                            'comply_or_explain_valid_at_time_of_report': False
                        })

            # give an idea how many endpoint issues there are compared to the total # of endpoints
            if endpoint_high:
                high_endpoints += 1
            if endpoint_medium:
                medium_endpoints += 1
            if endpoint_low:
                low_endpoints += 1
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
        url_scan_types = ["DNSSEC"]

        if url.id in url_scans:
            for scan in url_scans[url.id]:
                if scan.type in ['DNSSEC']:
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
                calculation = get_calculation(these_url_scans[url_scan_type])
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

        total_url_issues = url_issues_high + url_issues_medium + url_issues_low
        explained_total_url_issues = explained_url_issues_high + explained_url_issues_medium + explained_url_issues_low
        total_endpoint_issues = endpoint_issues_high + endpoint_issues_medium + endpoint_issues_low
        explained_total_endpoint_issues = \
            explained_endpoint_issues_high + explained_endpoint_issues_medium + explained_endpoint_issues_low

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
            "total_endpoints": total_endpoints,
            "high_endpoints": high_endpoints,
            "medium_endpoints": medium_endpoints,
            "low_endpoints": low_endpoints,
            "total_url_issues": total_url_issues,
            "url_issues_high": url_issues_high,
            "url_issues_medium": url_issues_medium,
            "url_issues_low": url_issues_low,
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

        save_url_rating(url, moment, total_high, total_medium, total_low, calculation,
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
                        explained_endpoint_issues_low=explained_endpoint_issues_low
                        )


def save_url_rating(url: Url, date: datetime, high: int, medium: int, low: int, calculation,
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
                    explained_endpoint_issues_medium: int = 0, explained_endpoint_issues_low: int = 0
                    ):
    u = UrlRating()
    u.url = url

    # save it as NOW if it's done today, else on the last moment on the same day.
    # So the url ratings immediately are shown, even if the day is not over.

    if date == datetime.now().date():
        u.when = datetime.now(pytz.utc)
    else:
        u.when = datetime(year=date.year, month=date.month, day=date.day,
                          hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)

    u.rating = 0
    u.calculation = calculation
    u.total_endpoints = total_endpoints

    u.high = high
    u.medium = medium
    u.low = low
    u.total_issues = total_issues
    u.high_endpoints = high_endpoints
    u.medium_endpoints = medium_endpoints
    u.low_endpoints = low_endpoints
    u.total_url_issues = total_url_issues
    u.total_endpoint_issues = total_endpoint_issues
    u.url_issues_high = url_issues_high
    u.url_issues_medium = url_issues_medium
    u.url_issues_low = url_issues_low
    u.endpoint_issues_high = endpoint_issues_high
    u.endpoint_issues_medium = endpoint_issues_medium
    u.endpoint_issues_low = endpoint_issues_low

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
                calculation = get_calculation(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'generic_url_scan' in timeline[moment]:
            message += "|  |- url generic_scan" + newline
            for item in timeline[moment]['generic_url_scan']['scans']:
                calculation = get_calculation(item)
                message += "|  |  |-  H:%2s M:%2s L:%2s %-40s" % (calculation.get('high', '?'),
                                                                  calculation.get('medium', '?'),
                                                                  calculation.get('low', '?'),
                                                                  item) + newline

        if 'generic_scan' in timeline[moment]:
            message += "|  |- endpoint generic_scan" + newline
            for item in timeline[moment]['generic_scan']['scans']:
                calculation = get_calculation(item)
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
def rate_organizations_now(organizations: List[Organization]):

    for organization in organizations:
        now = datetime.now(pytz.utc)
        rate_organization_on_moment(organization, now)


# also callable as admin action
# this is 100% based on url ratings, just an aggregate of the last status.
# make sure the URL ratings are up to date, they will check endpoints and such.
def rate_organization_on_moment(organization: Organization, when: datetime = None):
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    log.info("Creating report for %s on %s" % (organization, when, ))

    # if there already is an organization rating on this moment, skip it. You should have deleted it first.
    # this is probably a lot quicker than calculating the score and then deepdiffing it.
    # using this check we can also ditch deepdiff, because ratings on the same day are always the same.
    # todo: we should be able to continue on a certain day.
    if OrganizationRating.objects.all().filter(organization=organization, when=when).exists():
        log.info("Rating already exists for %s on %s. Not overwriting." % (organization, when))

    total_rating = 0
    total_high, total_medium, total_low = 0, 0, 0

    # Done: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_allinone(organization=organization, when=when)

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)

    total_urls, high_urls, medium_urls, low_urls = 0, 0, 0, 0
    total_endpoints, high_endpoints, medium_endpoints, low_endpoints = 0, 0, 0, 0

    # todo: both endpoints and urls are rated.
    url_calculations = []
    total_url_issues, total_endpoint_issues, url_issues_high, url_issues_medium = 0, 0, 0, 0
    url_issues_low, endpoint_issues_high, endpoint_issues_medium, endpoint_issues_low, = 0, 0, 0, 0

    for urlrating in all_url_ratings:
        total_rating += urlrating.rating
        total_high += urlrating.high
        total_medium += urlrating.medium
        total_low += urlrating.low

        total_endpoints += urlrating.total_endpoints
        high_endpoints += urlrating.high_endpoints
        medium_endpoints += urlrating.medium_endpoints
        low_endpoints += urlrating.low_endpoints

        total_url_issues += urlrating.total_url_issues
        total_endpoint_issues += urlrating.total_endpoint_issues
        url_issues_high += urlrating.url_issues_high
        url_issues_medium += urlrating.url_issues_medium
        url_issues_low += urlrating.url_issues_low
        endpoint_issues_high += urlrating.endpoint_issues_high
        endpoint_issues_medium += urlrating.endpoint_issues_medium
        endpoint_issues_low += urlrating.endpoint_issues_low

        total_urls += 1

        # url can only be in one category (otherwise there are urls in multiple categories which makes it
        # hard to display)
        if urlrating.high_endpoints:
            high_urls += 1
        elif urlrating.medium_endpoints:
            medium_urls += 1
        elif urlrating.low_endpoints:
            low_urls += 1

        url_calculations.append(urlrating.calculation)

    total_issues = total_high + total_medium + total_low

    # Still do deepdiff to prevent double reports.
    try:
        last = OrganizationRating.objects.filter(
            organization=organization, when__lte=when).latest('when')
    except OrganizationRating.DoesNotExist:
        log.debug("Could not find the last organization rating, creating a dummy one.")
        last = OrganizationRating()  # create an empty one

    calculation = {
        "organization": {
            "name": organization.name,
            "rating": total_rating,
            "high": total_high,
            "medium": total_medium,
            "low": total_low,
            "total_issues": total_issues,
            "urls": url_calculations,
            "total_urls": total_urls,
            "high_urls": high_urls,
            "medium_urls": medium_urls,
            "low_urls": low_urls,
            "total_endpoints": total_endpoints,
            "high_endpoints": high_endpoints,
            "medium_endpoints": medium_endpoints,
            "low_endpoints": low_endpoints,
            "total_url_issues": total_url_issues,
            "total_endpoint_issues": total_endpoint_issues,
            "url_issues_high": url_issues_high,
            "url_issues_medium": url_issues_medium,
            "url_issues_low": url_issues_low,
            "endpoint_issues_high": endpoint_issues_high,
            "endpoint_issues_medium": endpoint_issues_medium,
            "endpoint_issues_low": endpoint_issues_low
        }
    }

    # this is 10% faster without deepdiff, the major pain is elsewhere.
    if DeepDiff(last.calculation, calculation, ignore_order=True, report_repetition=True):

        log.debug("The calculation for %s on %s has changed, so we're saving this rating." % (organization, when))
        organizationrating = OrganizationRating()
        organizationrating.organization = organization
        organizationrating.rating = total_rating
        organizationrating.high = total_high
        organizationrating.medium = total_medium
        organizationrating.low = total_low
        organizationrating.when = when
        organizationrating.calculation = calculation

        organizationrating.total_issues = total_issues
        organizationrating.total_urls = total_urls
        organizationrating.high_urls = high_urls
        organizationrating.medium_urls = medium_urls
        organizationrating.low_urls = low_urls

        organizationrating.total_endpoints = total_endpoints
        organizationrating.high_endpoints = high_endpoints
        organizationrating.medium_endpoints = medium_endpoints
        organizationrating.low_endpoints = low_endpoints

        organizationrating.total_url_issues = total_url_issues
        organizationrating.total_endpoint_issues = total_endpoint_issues
        organizationrating.url_issues_high = url_issues_high
        organizationrating.url_issues_medium = url_issues_medium
        organizationrating.url_issues_low = url_issues_low
        organizationrating.endpoint_issues_high = endpoint_issues_high
        organizationrating.endpoint_issues_medium = endpoint_issues_medium
        organizationrating.endpoint_issues_low = endpoint_issues_low

        organizationrating.save()
    else:
        # This happens because some urls are dead etc: our filtering already removes this from the relevant information
        # at this point in time. But since it's still a significant moment, it will just show that nothing has changed.
        log.warning("The calculation for %s on %s is the same as the previous one. Not saving." % (organization, when))


def get_latest_urlratings_fast(urls: List[Url], when):
    # one query for all items. with sql injection feature.
    # perhaps we can do UrlRating.objects.raw( to avoid json loading.

    # prevent an empty IN query
    if not urls:
        return []

    sql = '''SELECT
                    id,
                    rating,
                    high,
                    medium,
                    low,
                    calculation
                FROM map_urlrating
                INNER JOIN
                  (SELECT MAX(id) as id2 FROM map_urlrating or2
                  WHERE `when` <= '%s' AND url_id IN (''' % (when, ) + ','.join(map(str, urls)) + ''')
                  GROUP BY url_id) as x
                  ON x.id2 = map_urlrating.id
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
    return UrlRating.objects.raw(sql)


def relevant_urls_at_timepoint_allinone(organization: Organization, when: datetime):
    # doing this, without the flat list results in about 40% faster execution, most notabily on large organizations
    # if you want to see what's going on, see relevant_urls_at_timepoint
    # removed the IN query to gain some extra speed
    # returned a flat list of pk's, since we don't do anything else with these urls. It's not particulary faster.
    both = Url.objects.filter(
        organization=organization).filter(
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

        when = organization.created_on if organization.created_on else FAILMAP_STARTED

        r = OrganizationRating()
        r.when = when
        r.rating = -1
        r.organization = organization
        r.calculation = {
            "organization": {
                "name": organization.name,
                "rating": "-1",
                "high": "0",
                "medium": "0",
                "low": "0",
                "urls": []
            }
        }
        r.save()


@app.task(queue='storage')
def calculate_vulnerability_statistics(days: int = 366):
    log.info("Calculation vulnerability graphs")

    # for everything that is displayed on the site:
    map_configurations = Configuration.objects.all().filter(
        is_displayed=True).order_by('display_order').values('country', 'organization_type')

    for map_configuration in map_configurations:
        scan_types = set()  # set instead of list to prevent checking if something is in there already.
        scan_types.add('total')  # the total would be separated per char if directly passed into set()
        scan_types.add('ftp')
        organization_type_id = map_configuration['organization_type']
        country = map_configuration['country']

        # for the entire year, starting with oldest (in case the other tasks are not ready)
        for days_back in list(reversed(range(0, days))):
            measurement = {'total': {'high': 0, 'medium': 0, 'low': 0}}
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            log.info("Days back:%s Date: %s" % (days_back, when))

            # delete this specific moment as it's going to be replaced, so it's not really noticable an update is
            # taking place.
            VulnerabilityStatistic.objects.all().filter(
                when=when, country=country, organization_type=OrganizationType(pk=organization_type_id)).delete()

            # about 1 second per query, while it seems to use indexes.
            # Also moved the calculation field here also from another table, which greatly improves joins on Mysql.
            # see map_data for more info.

            # this query removes the double urls (see below) and makes the joins straightforward. But it's way slower.
            # In the end this would be the query we should use... but can't right now
            # sql = """SELECT MAX(map_urlrating.id) as id, map_urlrating2.calculation FROM map_urlrating
            #        INNER JOIN url ON map_urlrating.url_id = url.id
            #        INNER JOIN url_organization on url.id = url_organization.url_id
            #        INNER JOIN organization ON url_organization.organization_id = organization.id
            #        INNER JOIN map_urlrating as map_urlrating2 ON map_urlrating2.id = map_urlrating.id
            #         WHERE organization.type_id = '%(OrganizationTypeId)s'
            #         AND organization.country = '%(country)s'
            #         AND map_urlrating.`when` <= '%(when)s'
            #         GROUP BY map_urlrating.url_id
            #     """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
            #            "country": get_country(country)}

            # parse the query here instead of outside the function to save a second or so.
            # The ID is included for convenience of the rawquery.
            # This query will deliver double ratings for urls that are doubly listed, which is dubious.
            # this happens because multiple organizations can have the same URL.
            # It's fair that there are more issues if more organizations share the same url?

            # you also have to include a filter on reagions that are not shown on the map anymore,
            # those are mostly dead organizations... that's why this query works on map data...

            # gets all url-ratings, even on urls that are dead / not relevant at a certain time period.
            # this doesn't really work out it seems... as you dont know what url ratings are relevant when
            sql = """SELECT map_urlrating.id as id, map_urlrating.id as my_id, map_urlrating.total_endpoints,
                            map_urlrating2.calculation as calculation, url.id as url_id2
                   FROM map_urlrating
                   INNER JOIN
                   (SELECT MAX(id) as id2 FROM map_urlrating or2
                   WHERE `when` <= '%(when)s' GROUP BY url_id) as x
                   ON x.id2 = map_urlrating.id
                   INNER JOIN url ON map_urlrating.url_id = url.id
                   INNER JOIN url_organization on url.id = url_organization.url_id
                   INNER JOIN organization ON url_organization.organization_id = organization.id
                   INNER JOIN map_urlrating as map_urlrating2 ON map_urlrating2.id = map_urlrating.id
                    WHERE organization.type_id = '%(OrganizationTypeId)s'
                    AND organization.country = '%(country)s'
                    AND map_urlrating.total_endpoints > 0
                    ORDER BY map_urlrating.url_id
                """ % {"when": when, "OrganizationTypeId": organization_type_id, "country": country}

            # There is a cartesian product on organization, for the simple reason that organizations sometimes
            # use the same url. The filter on organization cannot be changed to left outer join, because it might
            # remove relevant organizations.... it has to be a left outer join with the  WHERE filter included then.
            # Left joining doesnt' solve it because the link of url_organization. We might get a random organization
            # for the urlrating that fits it. But there should only be one organization per urlrating? No. Because
            # url ratings are shared amongst organization. That's why it works on the map, but not here.

            # So we're doing something else: filter out the url_ratings we've already processed in the python
            # code, which is slow and ugly. But for the moment it makes sense as the query is very complicated otherwise

            # so instead use the map data as a starter and dig down from that data.

            sql = """
                    SELECT
                        map_organizationrating.rating,
                        organization.name,
                        organizations_organizationtype.name,
                        coordinate_stack.area,
                        coordinate_stack.geoJsonType,
                        organization.id,
                        or3.calculation,
                        map_organizationrating.high,
                        map_organizationrating.medium,
                        map_organizationrating.low,
                        map_organizationrating.total_issues,
                        map_organizationrating.total_urls,
                        map_organizationrating.high_urls,
                        map_organizationrating.medium_urls,
                        map_organizationrating.low_urls
                    FROM map_organizationrating
                    INNER JOIN
                      (SELECT id as stacked_organization_id
                      FROM organization stacked_organization
                      WHERE (stacked_organization.created_on <= '%(when)s' AND stacked_organization.is_dead = 0)
                      OR (
                      '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
                      AND stacked_organization.is_dead = 1)) as organization_stack
                      ON organization_stack.stacked_organization_id = map_organizationrating.organization_id
                    INNER JOIN
                      organization on organization.id = stacked_organization_id
                    INNER JOIN
                      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
                    INNER JOIN
                      (SELECT MAX(id) as stacked_coordinate_id, area, geoJsonType, organization_id
                      FROM coordinate stacked_coordinate
                      WHERE (stacked_coordinate.created_on <= '%(when)s' AND stacked_coordinate.is_dead = 0)
                      OR
                      ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
                      AND stacked_coordinate.is_dead = 1) GROUP BY area, organization_id) as coordinate_stack
                      ON coordinate_stack.organization_id = map_organizationrating.organization_id
                    INNER JOIN
                      (SELECT MAX(id) as stacked_organizationrating_id FROM map_organizationrating
                      WHERE `when` <= '%(when)s' GROUP BY organization_id) as stacked_organizationrating
                      ON stacked_organizationrating.stacked_organizationrating_id = map_organizationrating.id
                    INNER JOIN map_organizationrating as or3 ON or3.id = map_organizationrating.id
                    WHERE organization.type_id = '%(OrganizationTypeId)s' AND organization.country= '%(country)s'
                    GROUP BY coordinate_stack.area, organization.name
                    ORDER BY map_organizationrating.`when` ASC
                    """ % {"when": when, "OrganizationTypeId": organization_type_id,
                           "country": country}

            organizationratings = OrganizationRating.objects.raw(sql)
            number_of_endpoints = 0
            number_of_urls = 0
            # log.debug(sql)

            log.info("Nr of urlratings: %s" % len(list(organizationratings)))

            # some urls are in multiple organizaitons, make sure that it's only shown once.
            processed_urls = []

            for organizationrating in organizationratings:

                # log.debug("Processing rating of %s " %
                #     organizationrating.calculation["organization"].get("name", "UNKOWN"))

                urlratings = organizationrating.calculation["organization"].get("urls", [])

                number_of_urls += len(urlratings)

                # group by vulnerability type
                for urlrating in urlratings:

                    # prevent the same urls counting double or more...
                    if urlrating["url"] in processed_urls:
                        # log.debug("Removed url because it's already in the report: %s" % urlrating["url"])
                        continue

                    processed_urls.append(urlrating["url"])

                    # log.debug("Url: %s" % (urlrating["url"]))

                    number_of_endpoints += len(urlrating["endpoints"])

                    # print(connection.queries)
                    # exit()

                    # www.kindpakket.groningen.nl is missing
                    # url reports
                    for rating in urlrating['ratings']:

                        # log.debug("- type: %s H: %s, M: %s, L: %s" %
                        #     (rating['type'], rating['high'], rating['medium'], rating['low']))

                        if rating['type'] not in measurement:
                            measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                        # if rating['type'] not in scan_types:
                        scan_types.add(rating['type'])

                        measurement[rating['type']]['high'] += rating['high']
                        measurement[rating['type']]['medium'] += rating['medium']
                        measurement[rating['type']]['low'] += rating['low']

                        measurement['total']['high'] += rating['high']
                        measurement['total']['medium'] += rating['medium']
                        measurement['total']['low'] += rating['low']

                    # endpoint reports
                    for endpoint in urlrating['endpoints']:

                        for rating in endpoint['ratings']:
                            if rating['type'] not in measurement:
                                measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                            # debugging, perhaps it appears that the latest scan is not set properly
                            # if rating['type'] == 'ftp' and rating['high']:
                            #     log.debug("High ftp added for %s" % urlrating["url"])

                            # if rating['type'] not in scan_types:
                            scan_types.add(rating['type'])

                            measurement[rating['type']]['high'] += rating['high']
                            measurement[rating['type']]['medium'] += rating['medium']
                            measurement[rating['type']]['low'] += rating['low']

                            measurement['total']['high'] += rating['high']
                            measurement['total']['medium'] += rating['medium']
                            measurement['total']['low'] += rating['low']

            # store these results per scan type, and only retrieve this per scan type...
            for scan_type in scan_types:
                # log.debug(scan_type)
                if scan_type in measurement:
                    vs = VulnerabilityStatistic()
                    vs.when = when
                    vs.organization_type = OrganizationType(pk=organization_type_id)
                    vs.country = country
                    vs.scan_type = scan_type
                    vs.high = measurement[scan_type]['high']
                    vs.medium = measurement[scan_type]['medium']
                    vs.low = measurement[scan_type]['low']
                    vs.urls = number_of_urls
                    vs.endpoints = number_of_endpoints
                    vs.save()


@app.task(queue='storage')
def calculate_map_data_today():
    calculate_map_data.si(1).apply_async()


@app.task(queue='storage')
def calculate_map_data(days: int = 366):
    log.info("calculate_map_data")

    # all vulnerabilities
    filters = ["security_headers_strict_transport_security", "security_headers_x_content_type_options", "ftp", "DNSSEC",
               "security_headers_x_frame_options", "security_headers_x_xss_protection", "tls_qualys", "plain_https",
               '', 'tls_qualys_certificate_trusted', 'tls_qualys_encryption_quality']

    map_configurations = Configuration.objects.all().filter(
        is_displayed=True).order_by('display_order').values('country', 'organization_type__name', 'organization_type')

    for map_configuration in map_configurations:
        for days_back in list(reversed(range(0, days))):
            when = datetime.now(pytz.utc) - timedelta(days=days_back)
            for filter in filters:

                # You can expect something to change each day. Therefore just store the map data each day.
                MapDataCache.objects.all().filter(
                    when=when, country=map_configuration['country'],
                    organization_type=OrganizationType(pk=map_configuration['organization_type']),
                    filters=[filter]
                ).delete()

                log.debug("Country: %s, Organization_type: %s, day: %s, date: %s, filter: %s" % (
                    map_configuration['country'], map_configuration['organization_type__name'],
                    days_back, when, filter
                ))
                data = get_map_data(map_configuration['country'], map_configuration['organization_type__name'],
                                    days_back, filter)

                from django.db import OperationalError

                try:
                    cached = MapDataCache()
                    cached.organization_type = OrganizationType(pk=map_configuration['organization_type'])
                    cached.country = map_configuration['country']
                    cached.filters = [filter]
                    cached.when = when
                    cached.dataset = data
                    cached.save()
                except OperationalError as a:
                    # The public user does not have permission to run insert statements....
                    log.exception(a)
