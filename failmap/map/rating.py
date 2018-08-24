import logging
from datetime import datetime
from typing import List

import pytz
from celery import group
from constance import config
from deepdiff import DeepDiff
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan, UrlGenericScan
from failmap.scanners.scanner.scanner import q_configurations_to_display

from ..celery import Task, app
from .calculate import get_calculation
from .models import OrganizationRating, UrlRating

log = logging.getLogger(__package__)


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

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(q_configurations_to_display('organization'), **organizations_filter)

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []
    for organization in organizations:
        urls = Url.objects.filter(q_configurations_to_display(), organization=organization, **urls_filter)
        if not urls:
            continue

        # make sure default organization rating is in place
        tasks.append(rerate_urls.si(urls)
                     | rerate_organizations.si([organization]))

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s" % organizations_filter)
        log.debug("Url filter: %s" % urls_filter)
        log.debug("urls to display: %s" % q_configurations_to_display())
        log.debug("organizatins to display: %s" % q_configurations_to_display('organization'))
        raise Exception('Applied filters resulted in no tasks!')

    task = group(tasks)

    return task


@app.task(queue='storage')
def rerate_urls(urls: List):
    """Remove the rating of one url and rebuild anew."""

    for url in urls:
        delete_url_ratings(url)
        rate_timeline(create_timeline(url), url)


@app.task(queue='storage')
def rerate_organizations(organizations: List):
    """Remove organization rating and rebuild anew."""

    for organization in organizations:
        delete_organization_ratings(organization)
        add_organization_rating(organizations=[organization], build_history=True)


@app.task(queue='storage')
def add_organization_rating(organizations: List[Organization], build_history: bool=False, when: datetime=None):
    """
    :param organizations: List of organization
    :param build_history: Optional. Find all relevant moments of this organization and create a rating
    :param when: Optional. Datetime, ignored if build_history is on
    :return:
    """

    if when:
        assert isinstance(when, datetime)

    for organization in organizations:
        log.info('Adding rating for organization %s', organization)
        if build_history:
            default_organization_rating(organizations=[organization])
            moments, happenings = significant_moments(organizations=[organization])
            for moment in moments:
                rate_organization_on_moment(organization, moment)
        else:
            rate_organization_on_moment(organization, when)


def add_url_rating(urls: List[Url], build_history: bool=False, when: datetime=None):

    if when:
        isinstance(when, datetime)

    for url in urls:
        if build_history:
            rate_timeline(create_timeline(url), url)
        else:
            rate_url(url, when)


def delete_url_ratings(url: Url):
    UrlRating.objects.all().filter(url=url).delete()


def delete_organization_ratings(organization: Organization):
    OrganizationRating.objects.all().filter(organization=organization).delete()


def significant_moments(organizations: List[Organization]=None, urls: List[Url]=None):
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
    if config.REPORT_INCLUDE_HTTP_TLS_QUALYS:
        tls_qualys_scans = TlsQualysScan.objects.all().filter(endpoint__url__in=urls).\
            prefetch_related("endpoint").defer("endpoint__url")
        tls_qualys_scan_dates = [x.rating_determined_on for x in tls_qualys_scans]
    else:
        tls_qualys_scans = []
        tls_qualys_scan_dates = []

    allowed_to_report = []
    if config.REPORT_INCLUDE_HTTP_MISSING_TLS:
        allowed_to_report.append("plain_https")
    if config.REPORT_INCLUDE_HTTP_HEADERS_HSTS:
        allowed_to_report.append("Strict-Transport-Security")
    if config.REPORT_INCLUDE_HTTP_HEADERS_XFO:
        allowed_to_report.append("X-Frame-Options")
    if config.REPORT_INCLUDE_HTTP_HEADERS_X_XSS:
        allowed_to_report.append("X-XSS-Protection")
    if config.REPORT_INCLUDE_HTTP_HEADERS_X_CONTENT:
        allowed_to_report.append("X-Content-Type-Options")
    if config.REPORT_INCLUDE_DNS_DNSSEC:
        allowed_to_report.append("DNSSEC")
    if config.REPORT_INCLUDE_FTP:
        allowed_to_report.append("ftp")

    generic_scans = EndpointGenericScan.objects.all().filter(type__in=allowed_to_report, endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    generic_scan_dates = [x.rating_determined_on for x in generic_scans]
    # this is not faster.
    # generic_scan_dates = list(generic_scans.values_list("rating_determined_on", flat=True))

    # url generic scans
    generic_url_scans = UrlGenericScan.objects.all().filter(type__in=allowed_to_report, url__in=urls).\
        prefetch_related("url")
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

    return moments, happenings


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
        if endpoint not in timeline[moment_date]["dead_endpoints"]:
            timeline[moment_date]["dead_endpoints"].append(endpoint)

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
        given_ratings = {}

        if ('url_not_resolvable' in timeline[moment] or 'url_is_dead' in timeline[moment]) \
                and url_was_once_rated:
            log.debug('Url became non-resolvable or dead. Adding an empty rating to lower the score of'
                      'this domain if it had a score. It has been cleaned up. (hooray)')
            # this is the end for the domain.
            default_calculation = {
                "url": {
                    "url": url.url,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "ratings": [],
                    "endpoints": [],
                    "total_endpoints": 0,
                    "high_endpoints": 0,
                    "medium_endpoints": 0,
                    "low_endpoints": 0,
                    "total_issues:": 0,
                    "total_url_issues": 0,
                    "total_endpoint_issues": 0,
                    "url_issues_high": 0,
                    "url_issues_medium": 0,
                    "url_issues_low": 0,
                    "endpoint_issues_high": 0,
                    "endpoint_issues_medium": 0,
                    "endpoint_issues_low": 0,
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
                # endpoints can die this moment
                if dead_endpoint in relevant_endpoints:
                    relevant_endpoints.remove(dead_endpoint)
                # remove the endpoint from the past
                if dead_endpoint in previous_endpoints:
                    previous_endpoints.remove(dead_endpoint)

        endpoint_scan_types = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options",
                               "X-XSS-Protection", "tls_qualys", "plain_https", "ftp"]

        total_endpoints, high_endpoints, medium_endpoints, low_endpoints = 0, 0, 0, 0

        # Some sums that will be saved as stats:
        endpoint_issues_high, endpoint_issues_medium, endpoint_issues_low = 0, 0, 0
        for endpoint in relevant_endpoints:
            total_endpoints += 1
            url_was_once_rated = True

            calculations = []
            these_endpoint_scans = {}
            if endpoint.id in endpoint_scans:
                for scan in endpoint_scans[endpoint.id]:
                    if isinstance(scan, TlsQualysScan):
                        these_endpoint_scans['tls_qualys'] = scan
                    if isinstance(scan, EndpointGenericScan):
                        if scan.type in ['Strict-Transport-Security', 'X-Content-Type-Options',
                                         'X-Frame-Options', 'X-XSS-Protection', 'plain_https', 'ftp']:
                            these_endpoint_scans[scan.type] = scan

            # enrich the ratings with previous ratings, without overwriting them.
            for endpoint_scan_type in endpoint_scan_types:
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
            for endpoint_scan_type in endpoint_scan_types:
                if endpoint_scan_type in these_endpoint_scans:
                    if endpoint_scan_type not in given_ratings[label]:
                        calculation = get_calculation(these_endpoint_scans[endpoint_scan_type])
                        if calculation:
                            calculations.append(calculation)
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
                            "last_scan": these_endpoint_scans[endpoint_scan_type].last_scan_moment.isoformat()
                        })

            # give an idea how many endpoint issues there are compared to the total # of endpoints
            if endpoint_high:
                high_endpoints += 1
            if endpoint_medium:
                medium_endpoints += 1
            if endpoint_low:
                low_endpoints += 1

            # Readibility is important: it's ordered from the worst to least points.
            calculations = sorted(calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

            endpoint_reports.append({
                "ip": endpoint.ip_version,
                "ip_version": endpoint.ip_version,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "v4": endpoint.is_ipv4(),
                "high": endpoint_high,
                "medium": endpoint_medium,
                "low": endpoint_low,
                "ratings": calculations
            })

        previous_endpoints += relevant_endpoints

        # prevent empty ratings cluttering the database and skewing the stats.
        # todo: only do this if there never was a urlrating before this.
        if not endpoint_reports and not url_was_once_rated:
            continue

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
                if isinstance(scan, UrlGenericScan):
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
        for url_scan_type in url_scan_types:
            if url_scan_type in these_url_scans:
                calculation = get_calculation(these_url_scans[url_scan_type])
                if calculation:
                    url_calculations.append(calculation)
                    url_issues_high += calculation["high"]
                    total_high += calculation["high"]
                    total_medium += calculation["medium"]
                    url_issues_medium += calculation["medium"]
                    total_low += calculation["low"]
                    url_issues_low += calculation["low"]

        total_url_issues = url_issues_high + url_issues_medium + url_issues_low
        total_endpoint_issues = endpoint_issues_high + endpoint_issues_medium + endpoint_issues_low

        sorted_url_reports = sorted(url_calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

        sorted_endpoints_reports = sorted(
            endpoint_reports, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

        total_issues = total_high + total_medium + total_low
        calculation = {
            "url": url.url,
            "high": total_high,
            "medium": total_medium,
            "low": total_low,
            "ratings": sorted_url_reports,
            "endpoints": sorted_endpoints_reports,
            "total_endpoints": total_endpoints,
            "high_endpoints": high_endpoints,
            "medium_endpoints": medium_endpoints,
            "low_endpoints": low_endpoints,
            "total_issues:": total_issues,

            "total_url_issues": total_url_issues,
            "total_endpoint_issues": total_endpoint_issues,
            "url_issues_high": url_issues_high,
            "url_issues_medium": url_issues_medium,
            "url_issues_low": url_issues_low,
            "endpoint_issues_high": endpoint_issues_high,
            "endpoint_issues_medium": endpoint_issues_medium,
            "endpoint_issues_low": endpoint_issues_low,
        }

        log.debug("On %s %s has %s endpoints and %s high, %s medium and %s low vulnerabilities" %
                  (moment, url, len(sorted_endpoints_reports), total_high, total_medium, total_low))

        save_url_rating(url, moment, total_high, total_medium, total_low, calculation,
                        total_issues=total_issues, total_endpoints=total_endpoints, high_endpoints=high_endpoints,
                        medium_endpoints=medium_endpoints, low_endpoints=low_endpoints,
                        total_url_issues=total_url_issues, total_endpoint_issues=total_endpoint_issues,
                        url_issues_high=url_issues_high, url_issues_medium=url_issues_medium,
                        url_issues_low=url_issues_low, endpoint_issues_high=endpoint_issues_high,
                        endpoint_issues_medium=endpoint_issues_medium, endpoint_issues_low=endpoint_issues_low
                        )


def save_url_rating(url: Url, date: datetime, high: int, medium: int, low: int, calculation,
                    total_issues: int=0, total_endpoints: int=0,
                    high_endpoints: int=0, medium_endpoints: int=0, low_endpoints: int=0,
                    total_url_issues: int=0, total_endpoint_issues: int=0,
                    url_issues_high: int=0, url_issues_medium: int=0, url_issues_low: int=0,
                    endpoint_issues_high: int=0, endpoint_issues_medium: int=0, endpoint_issues_low: int=0):
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
    u.high = high
    u.medium = medium
    u.low = low
    u.calculation = calculation
    u.total_endpoints = total_endpoints
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

    u.save()


def show_timeline_console(timeline, url: Url):
    newline = "\r\n"
    message = ""
    message += "" + newline
    message += url.url + newline
    for moment in timeline:

        message += "|" + newline
        message += "|- %s: %s" % (moment, timeline[moment]) + newline

        if 'tls_qualys' in timeline[moment]:
            message += "|  |- tls_qualys" + newline
            for item in timeline[moment]['tls_qualys']['endpoints']:
                message += "|  |  |- Endpoint %s" % item + newline
            for item in timeline[moment]['tls_qualys']['scans']:
                calculation = get_calculation(item)
                message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline

        if 'generic_scan' in timeline[moment]:
            message += "|  |- generic_scan" + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "plain_https":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s low: %s" % (calculation.high, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "Strict-Transport-Security":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Frame-Options":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Content-Type-Options":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-XSS-Protection":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "ftp":
                    calculation = get_calculation(item)
                    message += "|  |  |- %5s points: %s" % (calculation.high, item) + newline

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
    print(message)

    # first step to a UI
    return message


# also callable as admin action
# this is 100% based on url ratings, just an aggregate of the last status.
# make sure the URL ratings are up to date, they will check endpoints and such.
def rate_organization_on_moment(organization: Organization, when: datetime=None):
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    log.debug("rating on: %s, Organization %s" % (when, organization))

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

        if urlrating.high_endpoints:
            high_urls += 1
        if urlrating.medium_endpoints:
            medium_urls += 1
        if urlrating.low_endpoints:
            low_urls += 1

        url_calculations.append(urlrating.calculation)

    total_issues = total_high + total_medium + total_low

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


def get_latest_urlratings(urls: List[Url], when):
    # per item implementation, one query per item.
    all_url_ratings = []

    for url in urls:
        try:
            urlratings = UrlRating.objects.filter(url=url, when__lte=when)
            urlrating = urlratings.latest("when")  # kills the queryset, results 1
            all_url_ratings.append(urlrating)
        except UrlRating.DoesNotExist:
            log.debug("Url has no rating at this moment: %s %s" % (url, when))

    # https://stackoverflow.com/questions/403421/
    all_url_ratings.sort(key=lambda x: (x.high, x.medium, x.low), reverse=True)

    return all_url_ratings


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

    # cursor.execute(sql)
    # rows = cursor.fetchall()
    # for row in rows:
    #     data = {
    #         "rating": row[0],
    #         "high": row[1],
    #         "medium": row[2],
    #         "low": row[3],
#
    #         "calculation": json.loads(row[4]),
    #         # "calculation": row[4],
    #         "url": row[5],
    #     }
    #     all_url_ratings.append(data)
    # # print(all_url_ratings)
    # return all_url_ratings


# but this will give the correct score, possibly on the wrong endpoints (why?)
def rate_url(url: Url, when: datetime=None):
    if not when:
        when = datetime.now(pytz.utc)

    # contains since, last scan, rating, reason rating was given.
    explanation, rating = get_url_score_modular(url, when)

    # it's very possible there is no rating yet
    # we do show the not_resolvable history.
    try:
        last_url_rating = UrlRating.objects.filter(url=url,
                                                   url__urlrating__when__lte=when,
                                                   url__is_dead=False).latest("when")
    except ObjectDoesNotExist:
        # make sure there is no exception later on.
        last_url_rating = UrlRating()

    # avoid duplication. We think the explanation is the most unique identifier.
    # therefore the order in which URLs are grabbed (if there are new ones) is important.
    # it cannot be random, otherwise the explanation will be different every time.
    # deepdiff is also extremely slow, logically, since the json objects are pretty large.
    if explanation and DeepDiff(last_url_rating.calculation, explanation, ignore_order=True, report_repetition=True):
        u = UrlRating()
        u.url = url
        u.rating = rating
        u.when = when
        u.calculation = explanation
        u.save()
    else:
        log.warning("The calculation is still the same, not creating a new UrlRating")


def get_url_score_modular(url: Url, when: datetime=None):
    if not when:
        when = datetime.now(pytz.utc)

    log.debug("Calculating url score for %s on %s" % (url.url, when))

    """
    A relevant endpoint is an endpoint that is still alive or was alive at the time.
    Due to being alive (or at the time) it can get scores from various scanners more easily.

    Afterwards we'll check if at this time there also where dead endpoints.
    Dead endpoints add 0 points to the rating, but it can lower a rating.(?)
    """
    endpoints = relevant_endpoints_at_timepoint(url=url, when=when)

    # We're not going to have duplicate endpoints. This might happen if someone accidentally adds an
    # endpoint with the same info.
    # The solution before this was just to check on IP version. But the problem remains that scans
    # are connected to an endpoint. Reduction/merging of duplicate endpoints should take place elsewhere.
    processed_endpoints = []

    overall_high, overall_medium, overall_low = 0, 0, 0
    endpoint_calculations = []
    for endpoint in endpoints:
        endpoint_highs, endpoint_mediums, endpoint_lows = 0, 0, 0

        # protect from rating the same endpoints, if someone made a mistake and added a copy. See above comment.
        label = "%s%s%s" % (endpoint.is_ipv6(), endpoint.port, endpoint.protocol)
        if label not in processed_endpoints:
            processed_endpoints.append(label)
        else:
            continue

        scan_types = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                      "tls_qualys", "plain_https", "ftp"]

        calculations = []
        for scan_type in scan_types:
            calculation = endpoint_to_points_and_calculation(endpoint, when, scan_type)
            if calculation:
                calculations.append(calculation)
                endpoint_highs += calculation["high"]
                endpoint_mediums += calculation["medium"]
                endpoint_lows += calculation["low"]

        overall_high += endpoint_highs
        overall_medium += endpoint_mediums
        overall_low += endpoint_lows

        if calculations:
            endpoint_calculations.append({
                "ip": endpoint.ip_version,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "high": endpoint_highs,
                "medium": endpoint_mediums,
                "low": endpoint_lows,
                "ratings": calculations
            })

        else:
            log.debug('No tls or http rating at this moment. Not saving. %s %s' % (url, when))

    if not endpoints:
        log.error('No relevant endpoints at this time, probably didnt exist yet. %s %s' % (url, when))
        close_url_rating(url, when)

    if endpoint_calculations:
        url_rating_calculation = {
            "url": {
                "url": url.url,
                "high": overall_high,
                "medium": overall_medium,
                "low": overall_low,
                "endpoints": endpoint_calculations
            }
        }

        return url_rating_calculation, 0
    else:
        return {}, 0


def close_url_rating(url: Url, when: datetime):
    log.debug('Trying to close off the latest rating')
    """
    This creates url ratings for urls that have a rating, but where all endpoints went dead.

    Where the "get relevant endpoints" returns no endpoints anymore, and there has been a
    rating before. This function creates a rating with 0 points for the url. Things have
    apparently been cleaned up.

    This will be called a lot. Perhaps cache the results?
    :return:
    """

    # if did have score in past (we assume there was a check if there where endpoints before)
    # create 0 rating.

    default_calculation = {
        "url":
        {
            "url": url.url,
            "high": 0,
            "medium": 0,
            "low": 0,
            "endpoints": []
        }
    }

    try:
        urlratings = UrlRating.objects.filter(url=url, when__lte=when)
        urlrating = urlratings.latest("when")
        if DeepDiff(urlrating.calculation, default_calculation, ignore_order=True, report_repetition=True):
            log.debug('Added an empty zero rating. The url has probably been cleaned up.')
            x = UrlRating()
            x.calculation = default_calculation
            x.when = when
            x.url = url
            x.rating = 0
            x.save()
        else:
            log.debug('This was already cleaned up.')
    except ObjectDoesNotExist:
        log.debug('There where no prior ratings, so cannot close this url.')


def endpoint_to_points_and_calculation(endpoint: Endpoint, when: datetime, scan_type: str):
    try:
        scan = ""
        if scan_type in ["Strict-Transport-Security", "X-Content-Type-Options",
                         "X-Frame-Options", "X-XSS-Protection"]:
            scan = EndpointGenericScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when,
                                                      type=scan_type).latest('rating_determined_on')
        if scan_type == "plain_https":
            scan = EndpointGenericScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when,
                                                      type="plain_https").latest('rating_determined_on')
        if scan_type == "ftp":
            scan = EndpointGenericScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when,
                                                      type="ftp").latest('rating_determined_on')
        if scan_type == "tls_qualys":
            scan = TlsQualysScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when
                                                ).latest('rating_determined_on')

        calculation = get_calculation(scan)
        log.debug("On %s, Endpoint %s" % (when, endpoint))
        return calculation
    except ObjectDoesNotExist:
        log.debug("No %s scan on endpoint %s." % (scan_type, endpoint))
        return {}


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


# to save some database roundtrips
# @lru_cache(maxsize=None)  # TypeError: unhashable type: 'list'
def relevant_urls_at_timepoint(organizations: List[Organization], when: datetime):
    """
    It's possible that the url only has endpoints that are dead, but the URL resolves fine.

    :param organizations:
    :param when:
    :return:
    """

    urls = Url.objects.filter(organization__in=organizations)

    resolvable_in_the_past = urls.filter(
        created_on__lte=when,
        not_resolvable=True,
        not_resolvable_since__gte=when,
    )
    log.debug("Resolvable in the past:  %s" % resolvable_in_the_past.count())

    alive_in_the_past = urls.filter(
        created_on__lte=when,
        is_dead=True,
        is_dead_since__gte=when,
    )
    log.debug("Alive in the past:  %s" % alive_in_the_past.count())

    currently_alive_and_resolvable = urls.filter(
        created_on__lte=when,
        not_resolvable=False,
        is_dead=False,
    )  # or is_dead=False,
    log.debug("Alive urls:  %s" % currently_alive_and_resolvable.count())

    possibly_relevant_urls = (list(resolvable_in_the_past) +
                              list(alive_in_the_past) +
                              list(currently_alive_and_resolvable))

    relevant_urls = []
    for url in possibly_relevant_urls:
        # Check if they also had relevant endpoint. We do this separately to reduce the
        # complexity of history in queries and complexer ORM queries. It's slower, but easier to understand.
        # And using the lru_cache, it should be pretty fast (faster than having these subqueries executed
        # every time)
        has_endpoints = relevant_endpoints_at_timepoint(url=url, when=when)
        if has_endpoints:
            log.debug("The url %s is relevant on %s and has endpoints: " % (url, when))
            relevant_urls.append(url)
        else:
            log.debug("While the url %s was relevant on %s, it does not have any relevant endpoints." % (url, when))

    return relevant_urls


# to save some database roundtrips
# @lru_cache(maxsize=None)  # TypeError: unhashable type: 'list'
def relevant_endpoints_at_timepoint(url: Url, when: datetime):
    """
    The IN query is of course (a little bit) slower, so the function is called with a URL directly.
    Using two separate queries is also (a little bit) slower, so they are merged with a Q statement.

    Alive then:
    SELECT  "scanners_endpoint"."id", "scanners_endpoint"."url_id", "scanners_endpoint"."ip_version",
            "scanners_endpoint"."port", "scanners_endpoint"."protocol", "scanners_endpoint"."discovered_on",
            "scanners_endpoint"."is_dead", "scanners_endpoint"."is_dead_since", "scanners_endpoint"."is_dead_reason"
    FROM
            "scanners_endpoint"
    WHERE ( "scanners_endpoint"."url_id" IN (131)
    AND     "scanners_endpoint"."discovered_on" <= 2016-12-31 00:00:00 AND "scanners_endpoint"."is_dead" = True
    AND     "scanners_endpoint"."is_dead_since" >= 2016-12-31 00:00:00)

    Still alive endpoints:
    SELECT  "scanners_endpoint"."id", "scanners_endpoint"."url_id", "scanners_endpoint"."ip_version",
            "scanners_endpoint"."port", "scanners_endpoint"."protocol", "scanners_endpoint"."discovered_on",
            "scanners_endpoint"."is_dead", "scanners_endpoint"."is_dead_since", "scanners_endpoint"."is_dead_reason"
    FROM    "scanners_endpoint"
    WHERE ( "scanners_endpoint"."url_id" IN (131)
    AND     "scanners_endpoint"."discovered_on" <= 2016-12-31 00:00:00
    AND     "scanners_endpoint"."is_dead" = False)

    Both, with a Q construct:
    SELECT
            "scanners_endpoint"."id", "scanners_endpoint"."url_id", "scanners_endpoint"."ip_version",
            "scanners_endpoint"."port", "scanners_endpoint"."protocol", "scanners_endpoint"."discovered_on",
            "scanners_endpoint"."is_dead", "scanners_endpoint"."is_dead_since", "scanners_endpoint"."is_dead_reason"
    FROM    "scanners_endpoint"
    WHERE   ("scanners_endpoint"."url_id" IN (131)
    AND     (
                (   "scanners_endpoint"."discovered_on" <= 2016-12-31 00:00:00
                AND "scanners_endpoint"."is_dead" = False)
            OR
                (   "scanners_endpoint"."discovered_on" <= 2016-12-31 00:00:00
                AND "scanners_endpoint"."is_dead" = True
                AND "scanners_endpoint"."is_dead_since" >= 2016-12-31 00:00:00)))



    :param url:
    :param when:
    :return:
    """
    endpoints = Endpoint.objects.all()

    both = endpoints.filter(
        url=url).filter(
        # Alive then and still alive
        Q(discovered_on__lte=when, is_dead=False)
        |
        # Alive then
        Q(discovered_on__lte=when, is_dead=True, is_dead_since__gte=when))
    # print(both.query)  # looks legit.

    # log.debug("Endpoints alive back then and today (together): %s, " % (both.count()))

    # also saves on merging these:
    # relevant_endpoints = list(then_alive) + list(still_alive_endpoints)
    relevant_endpoints = list(both)

    # [log.debug("relevant endpoint for %s: %s" % (when, endpoint)) for endpoint in relevant_endpoints]

    return relevant_endpoints


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
