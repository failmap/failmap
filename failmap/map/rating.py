import logging
from datetime import datetime
from typing import List

import pytz
from celery import group
from deepdiff import DeepDiff
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan

from ..celery import Task, app
from .models import OrganizationRating, UrlRating
from .points_and_calculations import points_and_calculation

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    :param organizations_filter: dict: limit organizations to scan to these filters, see below
    :param urls_filter: dict: limit urls to scan to these filters, see below
    :param endpoints_filter: dict: limit endpoints to scan to these filters, see below

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a taskset will be composed to allow scanning of these items.

    By default all elegible items will be scanned. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> task = compose_task(organizations={'name__iexact': 'example'})
    >>> result = task.apply_async()
    >>> print(result.get())

    (`name__iexact` matches the name case-insensitive)

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> task = compose_task(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

    """

    if endpoints_filter:
        raise NotImplementedError('This scanner does not work on a endpoint level.')

    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(**organizations_filter)

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []
    for organization in organizations:
        urls = Url.objects.filter(organization=organization, **urls_filter)
        if not urls:
            continue

        tasks.append(rerate_urls.s(urls) | rerate_organizations.si([organization]))

    if not tasks:
        raise Exception('Applied filters resulted in no tasks!')

    task = group(tasks)

    return task


@app.task
def rerate_urls(urls: List):
    """Remove the rating of one url and rebuild anew."""

    for url in urls:
        delete_url_rating(url)
        rate_timeline(create_timeline(url), url)


@app.task
def rerate_organizations(organizations: List):
    """Remove organization rating and rebuild anew."""

    for organization in organizations:
        delete_organization_rating(organization)
    add_organization_rating(organizations)


@app.task
def rebuild_ratings_async(execute_locally: bool=True):
    """Remove all organization and url ratings, then rebuild them from scratch."""
    task = (rerate_urls_async.s(execute_locally=True) | rerate_organizations_async.si(execute_locally=True))
    task.apply_async()


@app.task
def add_organization_rating(organizations: List[Organization], build_history: bool=False, when: datetime=None):
    """
    :param organizations: List of organization
    :param build_history: Optional. Find all relevant moments of this organization and create a rating
    :param when: Optional. Datetime, ignored if build_history is on
    :return:
    """

    if when:
        isinstance(when, datetime)

    for organization in organizations:
        log.info('Adding rating for organization %s', organization)
        if build_history:
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


# @app.task
# def rerate_urls(urls: List[Url]=None):
#     if not urls:
#         urls = list(Url.objects.all().filter(is_dead=False).order_by('url'))
#
#     # to not have all ratings empty, do it per url
#     for url in urls:
#         delete_url_rating(url)
#         rate_timeline(create_timeline(url), url)


@app.task
def delete_url_rating(url: Url):
    UrlRating.objects.all().filter(url=url).delete()


@app.task
def delete_organization_rating(organization: Organization):
    OrganizationRating.objects.all().filter(organization=organization).delete()


@app.task
# 2.5 minutes and it's done :)
def rerate_urls_async(urls: List[Url]=None, execute_locally: bool=True):

    if not urls:
        urls = list(Url.objects.all().filter(is_dead=False).order_by('url'))

    tasks = []
    for url in urls:
        tasks.append((delete_url_rating.s(url) | create_timeline.si(url) | rate_timeline.s(url)))

    task = group(tasks)
    if execute_locally:
        task.apply_async()
    else:
        return task


@app.task
def rerate_organizations_async(organizations: List[Organization]=None, execute_locally: bool=True):
    if not organizations:
        organizations = list(Organization.objects.all().order_by('name'))

    # to not clear the whole map at once, do this per organization.
    # could be more efficient, but since the process is so slow, you'll end up with people looking at empty maps.
    tasks = [(default_ratings.si()
              | delete_organization_rating.si(organization)
              | add_organization_rating.si(organizations=[organization], build_history=True))
             for organization in organizations]

    task = group(tasks)
    if execute_locally:
        task.apply_async()
    else:
        return task


# @app.task
# def rerate_organizations(organizations: List[Organization]=None):
#     if not organizations:
#         organizations = list(Organization.objects.all().order_by('name'))
#
#     # to not clear the whole map at once, do this per organization.
#     # could be more efficient, but since the process is so slow, you'll end up with people looking at empty maps.
#     for organization in organizations:
#         OrganizationRating.objects.all().filter(organization=organization).delete()
#         default_ratings()
#         add_organization_rating(organizations=[organization], build_history=True)


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
    tls_qualys_scans = TlsQualysScan.objects.all().filter(endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    tls_qualys_scan_dates = [x.rating_determined_on for x in tls_qualys_scans]

    generic_scans = EndpointGenericScan.objects.all().filter(endpoint__url__in=urls).\
        prefetch_related("endpoint").defer("endpoint__url")
    generic_scan_dates = [x.rating_determined_on for x in generic_scans]
    # this is not faster.
    # generic_scan_dates = list(generic_scans.values_list("rating_determined_on", flat=True))

    dead_endpoints = Endpoint.objects.all().filter(url__in=urls, is_dead=True)
    dead_scan_dates = [x.is_dead_since for x in dead_endpoints]

    non_resolvable_urls = Url.objects.filter(not_resolvable=True, url__in=urls)
    non_resolvable_dates = [x.not_resolvable_since for x in non_resolvable_urls]

    dead_urls = Url.objects.filter(is_dead=True, url__in=urls)
    dead_url_dates = [x.is_dead_since for x in dead_urls]

    # reduce this to one moment per day only, otherwise there will be a report for every change
    # which is highly inefficient. Using the latest possible time of the day is used.
    moments = tls_qualys_scan_dates + generic_scan_dates + non_resolvable_dates + dead_scan_dates + dead_url_dates
    moments = [latest_moment_of_datetime(x) for x in moments]
    moments = sorted(set(moments))

    # If there are no scans at all, just return instead of storing useless junk or make other mistakes
    if not moments:
        return [], {
            'tls_qualys_scans': [],
            'generic_scans': [],
            'dead_endpoints': [],
            'non_resolvable_urls': [],
            'dead_urls': []
        }

    # make sure you don't save the scan for today at the end of the day (which would make it visible only at the end
    # of the day). Just make it "now" so you can immediately see the results.
    if moments[-1] == latest_moment_of_datetime(datetime.now()):
        moments[-1] = datetime.now(pytz.utc)

    log.debug("Moments found: %s", len(moments))

    # using scans, the query of "what scan happened when" doesn't need to be answered anymore.
    # the one thing is that scans have to be mapped to the moments (called a timeline)
    happenings = {
        'tls_qualys_scans': tls_qualys_scans,
        'generic_scans': generic_scans,
        'dead_endpoints': dead_endpoints,
        'non_resolvable_urls': non_resolvable_urls,
        'dead_urls': dead_urls
    }

    return moments, happenings


@app.task
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
        timeline[moment_date]['scans'] = []
        timeline[moment_date]["dead_endpoints"] = []

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
        timeline[some_day]['scans'].append(scan)

    # this code performs some date operations, which is much faster than using django's filter (as that hits the db)
    # for moment in [generic_scan.rating_determined_on for generic_scan in happenings['generic_scans']]:
    #     moment_date = moment.date()
    #     timeline[moment_date]["generic_scan"] = {}
    #     timeline[moment_date]["generic_scan"]["scanned"] = True
    #     scans = [x for x in happenings['generic_scans'] if x.rating_determined_on.date() == moment_date]
    #     timeline[moment_date]["generic_scan"]['scans'] = list(scans)
    #     endpoints = [x.endpoint for x in scans]
    #     timeline[moment_date]["generic_scan"]["endpoints"] = endpoints
    #     for endpoint in endpoints:
    #         if endpoint not in timeline[moment_date]["endpoints"]:
    #             timeline[moment_date]["endpoints"].append(endpoint)
    #     timeline[moment_date]['scans'] += scans

    for scan in happenings['tls_qualys_scans']:
        some_day = scan.rating_determined_on.date()

        # can we create this set in an easier way?
        if "tls_qualys" not in timeline[some_day]:
            timeline[some_day]["tls_qualys"] = {'scans': [], 'endpoints': []}

        timeline[some_day]["tls_qualys"]['scans'].append(scan)
        timeline[some_day]["tls_qualys"]["endpoints"].append(scan.endpoint)
        timeline[some_day]["endpoints"].append(scan.endpoint)
        timeline[some_day]['scans'].append(scan)

    # for moment in [tls_scan.rating_determined_on for tls_scan in happenings['tls_qualys_scans']]:
    #     moment_date = moment.date()
    #     timeline[moment_date]["tls_qualys"] = {}
    #     timeline[moment_date]["tls_qualys"]["scanned"] = True
    #     scans = [x for x in happenings['tls_qualys_scans'] if x.rating_determined_on.date() == moment_date]
    #     timeline[moment_date]["tls_qualys"]['scans'] = scans
    #     endpoints = [x.endpoint for x in scans]
    #     timeline[moment_date]["tls_qualys"]["endpoints"] = endpoints
    #     for endpoint in endpoints:
    #         if endpoint not in timeline[moment_date]["endpoints"]:
    #             timeline[moment_date]["endpoints"].append(endpoint)
    #     timeline[moment_date]['scans'] += scans

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

    # for moment in [dead_endpoint.is_dead_since for dead_endpoint in happenings['dead_endpoints']]:
    #     moment_date = moment.date()
    #     timeline[moment_date]["dead"] = True
    #     # figure out what endpoints died this moment
    #     for ep in happenings['dead_endpoints']:
    #         if ep.is_dead_since.date() == moment:
    #             if ep not in timeline[moment_date]["dead_endpoints"]:
    #                 timeline[moment_date]["dead_endpoints"].append(ep)

    # unique endpoints only
    for moment in moments:
        some_day = moment.date()
        timeline[some_day]["endpoints"] = list(set(timeline[some_day]["endpoints"]))

    # try to return dates in chronological order
    return timeline


def latest_moment_of_datetime(datetime_: datetime):
    return datetime_.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)


@app.task()
def rate_timeline(timeline, url: Url):
    log.info("Rebuilding ratings for url %s" % url)

    previous_ratings = {}
    previous_endpoints = []
    url_was_once_rated = False

    # work on a sorted timeline as otherwise this code is non-deterministic!
    for moment in sorted(timeline):
        total_scores, total_high, total_medium, total_low = 0, 0, 0, 0
        given_ratings = {}

        if ('url_not_resolvable' in timeline[moment].keys() or 'url_is_dead' in timeline[moment].keys()) \
                and url_was_once_rated:
            log.debug('Url became non-resolvable or dead. Adding an empty rating to lower the score of'
                      'this domain if it had a score. It has been cleaned up. (hooray)')
            # this is the end for the domain.
            default_calculation = {
                "url": {
                    "url": url.url,
                    "points": 0,
                    "endpoints": []
                }
            }

            save_url_rating(url, moment, 0, 0, 0, 0, default_calculation)
            return

        # reverse the relation: so we know all ratings per endpoint.
        # It is not really relevant what endpoints _really_ exist.
        endpoint_scans = {}
        for scan in timeline[moment]['scans']:
            endpoint_scans[scan.endpoint.id] = []

        for scan in timeline[moment]['scans']:
            endpoint_scans[scan.endpoint.id].append(scan)

        # create the report for this moment
        endpoint_calculations = []

        # also include all endpoints from the past time, which we do until the endpoints are dead.
        relevant_endpoints = set(timeline[moment]["endpoints"] + previous_endpoints)

        # remove dead endpoints
        # we don't need to remove the previous ratings, unless we want to save memory (Nah :))
        if "dead_endpoints" in timeline[moment].keys():
            for dead_endpoint in timeline[moment]["dead_endpoints"]:
                # endpoints can die this moment
                if dead_endpoint in relevant_endpoints:
                    relevant_endpoints.remove(dead_endpoint)
                # remove the endpoint from the past
                if dead_endpoint in previous_endpoints:
                    previous_endpoints.remove(dead_endpoint)

        scan_types = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                      "tls_qualys", "plain_https"]

        for endpoint in relevant_endpoints:
            url_was_once_rated = True

            calculations = []
            these_scans = {}
            if endpoint.id in endpoint_scans.keys():
                for scan in endpoint_scans[endpoint.id]:
                    if isinstance(scan, TlsQualysScan):
                        these_scans['tls_qualys'] = scan
                    if isinstance(scan, EndpointGenericScan):
                        if scan.type in ['Strict-Transport-Security', 'X-Content-Type-Options',
                                         'X-Frame-Options', 'X-XSS-Protection', 'plain_https']:
                            these_scans[scan.type] = scan

            # enrich the ratings with previous ratings, without overwriting them.
            for scan_type in scan_types:
                if scan_type not in these_scans.keys():
                    if endpoint.id in previous_ratings.keys():
                        if scan_type in previous_ratings[endpoint.id].keys():
                            these_scans[scan_type] = previous_ratings[endpoint.id][scan_type]

            # propagate the ratings to the next iteration.
            previous_ratings[endpoint.id] = {}
            previous_ratings[endpoint.id] = these_scans

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

            endpoint_scores, endpoint_high, endpoint_medium, endpoint_low = 0, 0, 0, 0

            for scan_type in scan_types:
                if scan_type in these_scans.keys():
                    if scan_type not in given_ratings[label]:
                        points, calculation = points_and_calculation(these_scans[scan_type])
                        if calculation:
                            calculations.append(calculation)
                            total_scores += points
                            endpoint_scores += points
                            endpoint_high += calculation["high"]
                            endpoint_medium += calculation["medium"]
                            endpoint_low += calculation["low"]
                            total_high += calculation["high"]
                            total_medium += calculation["medium"]
                            total_low += calculation["low"]

                        given_ratings[label].append(scan_type)
                    else:
                        calculations.append({
                            "type": scan_type,
                            "explanation": "Repeated finding. Probably because this url changed IP adresses or has "
                                           "multiple IP adresses (common for failover / load-balancing).",
                            "points": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 0,
                            "since": these_scans[scan_type].rating_determined_on.isoformat(),
                            "last_scan": these_scans[scan_type].last_scan_moment.isoformat()
                        })

            # Readibility is important: it's ordered from the worst to least points.
            calculations = sorted(calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

            endpoint_calculations.append({
                "ip": endpoint.ip_version,
                "ip_version": endpoint.ip_version,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "v4": endpoint.is_ipv4(),
                "points": endpoint_scores,
                "high": endpoint_high,
                "medium": endpoint_medium,
                "low": endpoint_low,
                "ratings": calculations
            })

        previous_endpoints += relevant_endpoints

        # prevent empty ratings cluttering the database and skewing the stats.
        # todo: only do this if there never was a urlrating before this.
        if not endpoint_calculations and not url_was_once_rated:
            continue

        sorted_endpoints = sorted(endpoint_calculations, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

        url_rating_json = {
            "url": url.url,
            "points": total_scores,
            "high": total_high,
            "medium": total_medium,
            "low": total_low,
            "endpoints": sorted_endpoints
        }

        log.debug("On %s this would score: %s " % (moment, total_scores), )

        save_url_rating(url, moment, total_scores, total_high, total_medium, total_low, url_rating_json)


def save_url_rating(url: Url, date: datetime, points: int, high: int, medium: int, low: int, calculation):
    u = UrlRating()
    u.url = url

    # save it as NOW if it's done today, else on the last moment on the same day.
    # So the url ratings immediately are shown, even if the day is not over.

    if date == datetime.now().date():
        u.when = datetime.now(pytz.utc)
    else:
        u.when = datetime(year=date.year, month=date.month, day=date.day,
                          hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)
    u.rating = points
    u.high = high
    u.medium = medium
    u.low = low
    u.calculation = calculation
    u.save()


def show_timeline_console(timeline, url: Url):
    newline = "\r\n"
    message = ""
    message += "" + newline
    message += url.url + newline
    for moment in timeline:

        message += "|" + newline
        message += "|- %s: %s" % (moment, timeline[moment].keys()) + newline

        if 'tls_qualys' in timeline[moment].keys():
            message += "|  |- tls_qualys" + newline
            for item in timeline[moment]['tls_qualys']['endpoints']:
                message += "|  |  |- Endpoint %s" % item + newline
            for item in timeline[moment]['tls_qualys']['scans']:
                score, calculation = points_and_calculation(item)
                message += "|  |  |- %5s points: %s" % (score, item) + newline

        if 'generic_scan' in timeline[moment].keys():
            message += "|  |- generic_scan" + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "plain_https":
                    score, calculation = points_and_calculation(item)
                    message += "|  |  |- %5s low: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "Strict-Transport-Security":
                    score, calculation = points_and_calculation(item)
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Frame-Options":
                    score, calculation = points_and_calculation(item)
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Content-Type-Options":
                    score, calculation = points_and_calculation(item)
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-XSS-Protection":
                    score, calculation = points_and_calculation(item)
                    message += "|  |  |- %5s points: %s" % (score, item) + newline

        if 'dead' in timeline[moment].keys():
            message += "|  |- dead endpoints" + newline
            for endpoint in timeline[moment]['dead_endpoints']:
                message += "|  |  |- %s" % endpoint + newline

        if 'url_not_resolvable' in timeline[moment].keys():
            message += "|  |- url became not resolvable" + newline

        if 'url_is_dead' in timeline[moment].keys():
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

    # todo: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_allinone(organization=organization, when=when)

    # testing if the lists are exactly the same.
    # for url in urls:
    #     if url not in urls_new:
    #         log.error(urls)
    #         log.error(urls_new)
    #         raise ArithmeticError("Urls are not the same... your logic is wrong.")
#
    # for url in urls_new:
    #     if url not in urls:
    #         log.error(urls)
    #         log.error(urls_new)
    #         raise ArithmeticError("Urls are not the same... your logic is wrong.")

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)

    url_calculations = []
    for urlrating in all_url_ratings:
        total_rating += urlrating.rating
        total_high += urlrating.high
        total_medium += urlrating.medium
        total_low += urlrating.low
        url_calculations.append(urlrating.calculation)

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
            "urls": url_calculations
        }
    }

    if DeepDiff(last.calculation, calculation, ignore_order=True, report_repetition=True):
        log.debug("The calculation (json) has changed, so we're saving this report, rating.")
        organizationrating = OrganizationRating()
        organizationrating.organization = organization
        organizationrating.rating = total_rating
        organizationrating.high = total_high
        organizationrating.medium = total_medium
        organizationrating.low = total_low
        organizationrating.when = when
        organizationrating.calculation = calculation
        organizationrating.save()
    else:
        # This happens because some urls are dead etc: our filtering already removes this from the relevant information
        # at this point in time. But since it's still a significant moment, it will just show that nothing has changed.
        log.warning("The calculation on %s is the same as the previous one. Not saving." % when)


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

    overall_points = 0
    overall_high, overall_medium, overall_low = 0, 0, 0
    endpoint_calculations = []
    for endpoint in endpoints:
        endpoint_points = 0
        endpoint_highs, endpoint_mediums, endpoint_lows = 0, 0, 0

        # protect from rating the same endpoints, if someone made a mistake and added a copy. See above comment.
        label = "%s%s%s" % (endpoint.is_ipv6(), endpoint.port, endpoint.protocol)
        if label not in processed_endpoints:
            processed_endpoints.append(label)
        else:
            continue

        scan_types = ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                      "tls_qualys", "plain_https"]

        calculations = []
        for scan_type in scan_types:
            points, calculation = endpoint_to_points_and_calculation(endpoint, when, scan_type)
            if calculation:
                calculations.append(calculation)
                endpoint_points += points
                endpoint_highs += calculation["high"]
                endpoint_mediums += calculation["medium"]
                endpoint_lows += calculation["low"]

        overall_points += endpoint_points
        overall_high += endpoint_highs
        overall_medium += endpoint_mediums
        overall_low += endpoint_lows

        if calculations:
            endpoint_calculations.append({
                "ip": endpoint.ip_version,
                "port": endpoint.port,
                "protocol": endpoint.protocol,
                "points": endpoint_points,
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
                "points": overall_points,
                "high": overall_high,
                "medium": overall_medium,
                "low": overall_low,
                "endpoints": endpoint_calculations
            }
        }

        return url_rating_calculation, overall_points
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
            "points": 0,
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
        if scan_type == "tls_qualys":
            scan = TlsQualysScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when
                                                ).latest('rating_determined_on')

        points, calculation = points_and_calculation(scan)
        log.debug("On %s, Endpoint %s, Points %s" % (when, endpoint, points))
        return int(points), str(calculation)
    except ObjectDoesNotExist:
        log.debug("No %s scan on endpoint %s." % (scan_type, endpoint))
        return 0, {}


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

    # Alive then
    # then_alive = endpoints.filter(
    #     url=url,
    #     discovered_on__lte=when,
    #     is_dead=True,
    #     is_dead_since__gte=when,
    # )
    # print(then_alive.query)

    # Alive then and still alive
    # still_alive_endpoints = endpoints.filter(
    #     url=url,
    #     discovered_on__lte=when,
    #     is_dead=False,
    # )
    # print(still_alive_endpoints.query)

    # let's mix both queries into a single one, saving a database roundtrip:
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


# todo: use the organization creation date for this.
@app.task
def default_ratings():
    """
    Generate default ratings so all organizations are on the map (as being grey). This prevents
    empty spots / holes.
    :return:
    """
    when = datetime(year=2016, month=1, day=1, hour=13, minute=37, second=42, tzinfo=pytz.utc)
    organizations = Organization.objects.all().exclude(organizationrating__when=when)
    for organization in organizations:
        log.info("Giving organization a default rating: %s" % organization)
        r = OrganizationRating()
        r.when = when
        r.rating = -1
        r.organization = organization
        r.calculation = {
            "organization": {
                "name": organization.name,
                "rating": "-1",
                "urls": []
            }
        }

        r.save()
