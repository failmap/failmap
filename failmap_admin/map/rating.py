import logging
from datetime import datetime
from typing import List

import pytz
from deepdiff import DeepDiff
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan

from ..celery import app
from .models import OrganizationRating, UrlRating
from .points_and_calculations import points_and_calculation

# from functools import lru_cache

logger = logging.getLogger(__package__)
"""
python -m cProfile -s time `which failmap-admin` rebuild-ratings
mainly SQL queries (still)

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
   186699   50.724    0.000   61.517    0.000 base.py:324(execute)
    30872   31.178    0.001   31.178    0.001 {method 'commit' of 'sqlite3.Connection' objects}
6499892/6498375   11.051    0.000   11.676    0.000 {built-in method builtins.hasattr}
6952977/6930265    9.602    0.000    9.632    0.000 {built-in method builtins.getattr}
1832647/1419376    7.205    0.000   51.009    0.000 compiler.py:368(compile)
   213054    6.303    0.000   11.092    0.000 query.py:266(clone)
  2860662    6.152    0.000   10.844    0.000 compiler.py:351(quote_name_unless_alias)
8490147/8489630    5.820    0.000    9.672    0.000 {built-in method builtins.isinstance}
  1139637    4.941    0.000    5.813    0.000 operations.py:199(get_db_converters)
   117238    4.884    0.000   15.216    0.000 compiler.py:523(get_default_columns)
173027/173005    4.818    0.000   43.225    0.000 query.py:1122(build_filter)
   186699    4.645    0.000   78.305    0.000 utils.py:77(execute)
   125021    4.598    0.000   43.696    0.000 compiler.py:165(get_select)
   170439    4.413    0.000    8.271    0.000 base.py:473(__init__)
  1308273    4.337    0.000    7.837    0.000 __init__.py:353(get_col)
     8322    4.188    0.001   80.269    0.010 rating.py:262(rate_timeline)
   349379    3.985    0.000    7.710    0.000 query.py:1284(names_to_path)
  1336234    3.972    0.000   14.358    0.000 expressions.py:693(as_sql)
   175012    3.905    0.000    4.338    0.000 query.py:128(__init__)
   124954    3.698    0.000   18.109    0.000 compiler.py:812(get_converters)
125021/124955    3.487    0.000   85.670    0.001 compiler.py:413(as_sql)
193674/129098    3.486    0.000   59.677    0.000 query.py:1255(_add_q)
   265136    3.428    0.000  197.598    0.001 query.py:47(__iter__)
   156383    3.403    0.000    3.404    0.000 {method 'sub' of '_sre.SRE_Pattern' objects}
   247487    3.176    0.000    8.180    0.000 dateparse.py:85(parse_datetime)
  2440240    3.124    0.000    4.241    0.000 __init__.py:471(__eq__)
   155826    2.981    0.000    2.981    0.000 {method 'execute' of 'sqlite3.Cursor' objects}
   133288    2.888    0.000  171.005    0.001 compiler.py:855(execute_sql)
  1539350    2.870    0.000    4.268    0.000 operations.py:147(quote_name)
  1131921    2.811    0.000    8.557    0.000 expressions.py:703(get_db_converters)
   199980    2.748    0.000    6.912    0.000 {method 'fetchmany' of 'sqlite3.Cursor' objects}
   200977    2.562    0.000   12.755    0.000 lookups.py:158(process_lhs)
   513049    2.560    0.000    3.892    0.000 related.py:651(foreign_related_fields)
   365765    2.280    0.000    2.280    0.000 {method 'replace' of 'datetime.datetime' objects}
   214624    2.261    0.000  200.017    0.001 query.py:1116(_fetch_all)
    45086    2.256    0.000    2.256    0.000 encoder.py:204(iterencode)
   522577    2.193    0.000    3.852    0.000 abc.py:178(__instancecheck__)
  8729938    2.179    0.000    2.179    0.000 {method 'append' of 'list' objects}
    60022    2.170    0.000    3.349    0.000 __init__.py:145(__init__)
   349455    2.046    0.000    5.804    0.000 query.py:161(__init__)
   322815    2.032    0.000    2.784    0.000 query_utils.py:63(__init__)
   346977    1.943    0.000    1.943    0.000 {method 'match' of '_sre.SRE_Pattern' objects}
  1077582    1.873    0.000    1.873    0.000 tree.py:21(__init__)
   205326    1.808    0.000   13.385    0.000 query.py:1102(_clone)
   988849    1.799    0.000  135.076    0.000 related_descriptors.py:161(__get__)
     8322    1.793    0.000  267.225    0.032 rating.py:167(create_timeline)

"""


@app.task
def rebuild_ratings():
    """Remove all organization and url ratings, then rebuild them from scratch."""
    rerate_urls()
    rerate_organizations()


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


def rerate_urls(urls: List[Url]=None):
    if not urls:
        urls = list(Url.objects.all().filter(is_dead=False).order_by('url'))

    # to not have all ratings empty, do it per url
    for url in urls:
        UrlRating.objects.all().filter(url=url).delete()
        rate_timeline(create_timeline(url), url)


def rerate_organizations(organizations: List[Organization]=None):
    if not organizations:
        organizations = list(Organization.objects.all().order_by('name'))

    # to not clear the whole map at once, do this per organization.
    # could be more efficient, but since the process is so slow, you'll end up with people looking at empty maps.
    for organization in organizations:
        OrganizationRating.objects.all().filter(organization=organization).delete()
        default_ratings()
        add_organization_rating([organization], build_history=True)


def rerate_urls_of_organizations(organizations: List[Organization]):
    rerate_urls(Url.objects.filter(is_dead=False, organization__in=organizations).order_by('url'))


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
        logger.debug("Getting all urls from organization: %s" % organizations)
        urls = Url.objects.filter(organization__in=organizations)
    if urls:
        logger.debug("Getting all url: %s" % urls)

    if not urls:
        logger.info("Could not find urls from organization or url.")
        return []

    tls_qualys_scans = TlsQualysScan.objects.all().filter(endpoint__url__in=urls)
    tls_qualys_scan_dates = [x.rating_determined_on for x in tls_qualys_scans]

    generic_scans = EndpointGenericScan.objects.all().filter(endpoint__url__in=urls)
    generic_scan_dates = [x.rating_determined_on for x in generic_scans]

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

    logger.debug("Moments found: %s", len(moments))

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
        timeline[moment.date()] = {}
        timeline[moment.date()]["endpoints"] = []
        timeline[moment.date()]['scans'] = []
        timeline[moment.date()]["dead_endpoints"] = []

    # sometimes there have been scans on dead endpoints. This is a problem in the database.
    # this code is correct with retrieving those endpoints again.
    # we could save a list of dead endpoints, but the catch is that an endpoint can start living
    # again over time. The scans with only dead endpoints should not be made.

    # this code performs some date operations, which is much faster than using django's filter (as that hits the db)
    for moment in [generic_scan.rating_determined_on for generic_scan in happenings['generic_scans']]:
        moment = moment.date()
        timeline[moment]["generic_scan"] = {}
        timeline[moment]["generic_scan"]["scanned"] = True
        scans = [x for x in happenings['generic_scans'] if x.rating_determined_on.date() == moment]
        timeline[moment]["generic_scan"]['scans'] = list(scans)
        endpoints = [x.endpoint for x in scans]
        timeline[moment]["generic_scan"]["endpoints"] = endpoints
        for endpoint in endpoints:
            if endpoint not in timeline[moment]["endpoints"]:
                timeline[moment]["endpoints"].append(endpoint)
        timeline[moment]['scans'] += list(scans)

    for moment in [tls_scan.rating_determined_on for tls_scan in happenings['tls_qualys_scans']]:
        moment = moment.date()
        timeline[moment]["tls_qualys"] = {}
        timeline[moment]["tls_qualys"]["scanned"] = True
        scans = [x for x in happenings['tls_qualys_scans'] if x.rating_determined_on.date() == moment]
        timeline[moment]["tls_qualys"]['scans'] = scans
        endpoints = [x.endpoint for x in scans]
        timeline[moment]["tls_qualys"]["endpoints"] = endpoints
        for endpoint in endpoints:
            if endpoint not in timeline[moment]["endpoints"]:
                timeline[moment]["endpoints"].append(endpoint)
        timeline[moment]['scans'] += list(scans)

    # Any endpoint from this point on should be removed. If the url becomes alive again, add it again, so you can
    # see there are gaps in using the url over time. Which is more truthful.
    for moment in [not_resolvable_url.not_resolvable_since for not_resolvable_url in happenings['non_resolvable_urls']]:
        moment = moment.date()
        timeline[moment]["url_not_resolvable"] = True

    for moment in [dead_url.is_dead_since for dead_url in happenings['dead_urls']]:
        moment = moment.date()
        timeline[moment]["url_is_dead"] = True

    for moment in [dead_endpoint.is_dead_since for dead_endpoint in happenings['dead_endpoints']]:
        moment = moment.date()
        timeline[moment]["dead"] = True
        # figure out what endpoints died this moment
        for ep in happenings['dead_endpoints']:
            if ep.is_dead_since.date() == moment:
                if ep not in timeline[moment]["dead_endpoints"]:
                    timeline[moment]["dead_endpoints"].append(ep)

    # unique endpoints only
    for moment in moments:
        timeline[moment.date()]["endpoints"] = list(set(timeline[moment.date()]["endpoints"]))

    # try to return dates in chronological order
    return timeline


def latest_moment_of_datetime(datetime_: datetime):
    return datetime_.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)


def rate_timeline(timeline, url: Url):
    logger.info("Rebuilding ratings for for %s" % url)

    previous_ratings = {}
    previous_endpoints = []
    url_was_once_rated = False

    # work on a sorted timeline as otherwise this code is non-deterministic!
    for moment in sorted(timeline):
        total_scores, total_high, total_medium, total_low = 0, 0, 0, 0
        given_ratings = {}

        if ('url_not_resolvable' in timeline[moment].keys() or 'url_is_dead' in timeline[moment].keys()) \
                and url_was_once_rated:
            logger.debug('Url became non-resolvable or dead. Adding an empty rating to lower the score of'
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
                        points, calculation = points_and_calculation(these_scans[scan_type], scan_type)
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

        logger.debug("On %s this would score: %s " % (moment, total_scores), )

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
                score, json = points_and_calculation(item, 'tls_qualys')
                message += "|  |  |- %5s points: %s" % (score, item) + newline

        if 'generic_scan' in timeline[moment].keys():
            message += "|  |- generic_scan" + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "plain_https":
                    score, json = points_and_calculation(item, 'plain_https')
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "Strict-Transport-Security":
                    score, json = points_and_calculation(item, "Strict-Transport-Security")
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Frame-Options":
                    score, json = points_and_calculation(item, "X-Frame-Options")
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-Content-Type-Options":
                    score, json = points_and_calculation(item, "X-Content-Type-Options")
                    message += "|  |  |- %5s points: %s" % (score, item) + newline
            for item in timeline[moment]['generic_scan']['scans']:
                if item.type == "X-XSS-Protection":
                    score, json = points_and_calculation(item, "X-XSS-Protection")
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

    logger.debug("rating on: %s, Organization %s" % (when, organization))

    total_rating = 0
    total_high, total_medium, total_low = 0, 0, 0

    # todo: closing off urls, after no relevant endpoints, but still resolvable. Done.
    urls = relevant_urls_at_timepoint(organizations=[organization], when=when)

    all_url_ratings = []
    url_calculations = []
    for url in urls:
        try:
            urlratings = UrlRating.objects.filter(url=url, when__lte=when)
            urlrating = urlratings.latest("when")  # kills the queryset, results 1
            all_url_ratings.append(urlrating)
        except UrlRating.DoesNotExist:
            logger.warning("Url has no rating at this moment: %s %s" % (url, when))

    # sort all_url_ratings on rating desc.
    # https://stackoverflow.com/questions/403421/
    all_url_ratings.sort(key=lambda x: (x.high, x.medium, x.low), reverse=True)

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
        logger.debug("Could not find the last organization rating, creating a dummy one.")
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
        logger.debug("The calculation (json) has changed, so we're saving this report, rating.")
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
        logger.warning("The calculation is still the same, not creating a new OrganizationRating")


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
    if explanation and DeepDiff(last_url_rating.calculation, explanation, ignore_order=True, report_repetition=True):
        u = UrlRating()
        u.url = url
        u.rating = rating
        u.when = when
        u.calculation = explanation
        u.save()
    else:
        logger.warning("The calculation is still the same, not creating a new UrlRating")


def get_url_score_modular(url: Url, when: datetime=None):
    if not when:
        when = datetime.now(pytz.utc)

    logger.debug("Calculating url score for %s on %s" % (url.url, when))

    """
    A relevant endpoint is an endpoint that is still alive or was alive at the time.
    Due to being alive (or at the time) it can get scores from various scanners more easily.

    Afterwards we'll check if at this time there also where dead endpoints.
    Dead endpoints add 0 points to the rating, but it can lower a rating.(?)
    """
    endpoints = relevant_endpoints_at_timepoint([url], when)

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
            logger.debug('No tls or http rating at this moment. Not saving. %s %s' % (url, when))

    if not endpoints:
        logger.error('No relevant endpoints at this time, probably didnt exist yet. %s %s' % (url, when))
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
    logger.debug('Trying to close off the latest rating')
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
            logger.debug('Added an empty zero rating. The url has probably been cleaned up.')
            x = UrlRating()
            x.calculation = default_calculation
            x.when = when
            x.url = url
            x.rating = 0
            x.save()
        else:
            logger.debug('This was already cleaned up.')
    except ObjectDoesNotExist:
        logger.debug('There where no prior ratings, so cannot close this url.')


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

        points, calculation = points_and_calculation(scan, scan_type)
        logger.debug("On %s, Endpoint %s, Points %s" % (when, endpoint, points))
        return int(points), str(calculation)
    except ObjectDoesNotExist:
        logger.debug("No %s scan on endpoint %s." % (scan_type, endpoint))
        return 0, {}


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
    logger.debug("Resolvable in the past:  %s" % resolvable_in_the_past.count())

    alive_in_the_past = urls.filter(
        created_on__lte=when,
        is_dead=True,
        is_dead_since__gte=when,
    )
    logger.debug("Alive in the past:  %s" % alive_in_the_past.count())

    currently_alive_and_resolvable = urls.filter(
        created_on__lte=when,
        not_resolvable=False,
        is_dead=False,
    )  # or is_dead=False,
    logger.debug("Alive urls:  %s" % currently_alive_and_resolvable.count())

    possibly_relevant_urls = (list(resolvable_in_the_past) +
                              list(alive_in_the_past) +
                              list(currently_alive_and_resolvable))

    relevant_urls = []
    for url in possibly_relevant_urls:
        # Check if they also had relevant endpoint. We do this separately to reduce the
        # complexity of history in queries and complexer ORM queries. It's slower, but easier to understand.
        # And using the lru_cache, it should be pretty fast (faster than having these subqueries executed
        # every time)
        has_endpoints = relevant_endpoints_at_timepoint(urls=[url], when=when)
        if has_endpoints:
            logger.debug("The url %s is relevant on %s and has endpoints: " % (url, when))
            relevant_urls.append(url)
        else:
            logger.debug("While the url %s was relevant on %s, it does not have any relevant endpoints." % (url, when))

    return relevant_urls


# to save some database roundtrips
# @lru_cache(maxsize=None)  # TypeError: unhashable type: 'list'
def relevant_endpoints_at_timepoint(urls: List[Url], when: datetime):
    endpoints = Endpoint.objects.all()

    # Alive then
    then_alive = endpoints.filter(
        url__in=urls,
        discovered_on__lte=when,
        is_dead=True,
        is_dead_since__gte=when,
    )

    # Alive then and still alive
    still_alive_endpoints = endpoints.filter(
        url__in=urls,
        discovered_on__lte=when,
        is_dead=False,
    )

    logger.debug("Endpoints alive back then:  %s, Still alive today: %s" % (
        then_alive.count(), still_alive_endpoints.count()))

    relevant_endpoints = list(then_alive) + list(still_alive_endpoints)

    [logger.debug("relevant endpoint for %s: %s" % (when, endpoint)) for endpoint in relevant_endpoints]

    return relevant_endpoints


# todo: use the organization creation date for this.
def default_ratings():
    """
    Generate default ratings so all organizations are on the map (as being grey). This prevents
    empty spots / holes.
    :return:
    """
    when = datetime(year=2016, month=1, day=1, hour=13, minute=37, second=42, tzinfo=pytz.utc)
    organizations = Organization.objects.all().exclude(organizationrating__when=when)
    for organization in organizations:
        logger.info("Giving organization a default rating: %s" % organization)
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