import json as xjson
import logging
from datetime import datetime

import pytz
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta  # history
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan

from .models import OrganizationRating, UrlRating

logger = logging.getLogger(__package__)

"""
Here the magic happens for determining a rating for a url and ultimately an organization.

How we approach this: we first make daily ratings for the last days and store them
    except if it results in the same rating as previous.

"""


def get_weekly_intervals():
    # for the past year, create a rating every week for all organizations
    now = datetime.now(pytz.utc)

    # the approach with a counter (i) is a very naive approach. A faster way would be to check
    # when things where changed in the rating and only record those changes.
    # The downside is that could be more complex as there are more scanners... perhaps..
    times = []
    try:
        firstscan = TlsQualysScan.objects.all().earliest(field_name="scan_date")
        naive_date = datetime.combine(firstscan.scan_date, datetime.min.time())
        good_date = pytz.utc.localize(naive_date)
        i = (now - good_date).days

        # add an extra week to be sure you've got everything.
        i = i + 7
    except ObjectDoesNotExist:
        # todo: narrow down overly broad exceptions
        # no first scan? then just have some value....
        i = 365

    print("Going back %s days in time." % i)

    while i > 0:
        times.append(now - relativedelta(days=i))
        i -= 7

    return times


def rate_organizations(create_history=False):
    times = get_weekly_intervals() if create_history else [
        datetime.now(pytz.utc)]

    os = Organization.objects.all()
    for when in times:
        for o in os:
            rate_organization(o, when)


def rate_organizations_efficient(create_history=False):
    os = Organization.objects.all().order_by('name')
    if create_history:
        for o in os:
            times = significant_times(organization=o)
            for time in times:
                rate_organization(o, time)
    else:
        for o in os:
            rate_organization(o, datetime.now(pytz.utc))


def rate_organization_efficient(organization, create_history=False):
    if create_history:
        times = significant_times(organization=organization)
        for time in times:
            rate_organization(organization, time)
    else:
        rate_organization(organization, datetime.now(pytz.utc))


def rerate_existing_urls_of_organization(organization):
    UrlRating.objects.all().filter(url__organization=organization).delete()
    urls = Url.objects.filter(is_dead=False, organization=organization).order_by('url')
    for url in urls:
        rerate_url_with_timeline(url)


def rerate_existing_urls():
    UrlRating.objects.all().delete()
    urls = Url.objects.filter(is_dead=False).order_by('url')
    for url in urls:
        rate_timeline(timeline(url), url)


def clear_all_organization_ratings():
    OrganizationRating.objects.all().delete()


def rerate_url_with_timeline(url):
    UrlRating.objects.all().filter(url=url).delete()
    rate_timeline(timeline(url), url)


def timeline(url):
    """
    Searches for all significant point in times that something changed. The goal is to save
    unneeded queries when rebuilding ratings. When you know when things changed, you know
    at what moments you need to create reports.

    Another benefit is not only less queries, but also more granularity for reporting: not just
    per week, but known per day.

    We want to know:
    - When a rating was made, since only changes are saved, all those datapoints.
    - - This implies when the url was alive (at least after a positive result).
    - When a url was not resolvable (aka: is not in the report anymore)

    The timeline helps with more efficient ratings (less database time)

    A timeline looks like this:
    date - things that changed

    01-01-2017 - endpoint added

    01-02-2017 - TLS scan Update
    01-04-2017 - TLS scan update
                 HTTP Scan update

    :return:
    """

    tls_qualys_scan_dates = []
    try:
        tls_qualys_scans = TlsQualysScan.objects.all().filter(endpoint__url=url)
        tls_qualys_scan_dates = [x.rating_determined_on for x in tls_qualys_scans]
        # logger.debug("tls_qualys_scan_dates: %s" % tls_qualys_scan_dates)
    except ObjectDoesNotExist:
        # no tls scans
        pass

    generic_scan_dates = []
    try:
        generic_scans = EndpointGenericScan.objects.all().filter(endpoint__url=url)
        generic_scan_dates = [x.rating_determined_on for x in generic_scans]
        # logger.debug("generic_scan_dates: %s" % generic_scan_dates)
    except ObjectDoesNotExist:
        # no generic scans
        pass

    dead_scan_dates = []
    dead_scans = []
    try:
        dead_scans = Endpoint.objects.all().filter(url=url, is_dead=True)
        dead_scan_dates = [x.is_dead_since for x in dead_scans]
        # logger.debug("dead_scan_dates: %s" % dead_scan_dates)
    except ObjectDoesNotExist:
        # no generic scans
        pass

    # is this relevant? I think we can do without.
    non_resolvable_dates = []
    try:
        non_resolvable_urls = Url.objects.filter(not_resolvable=True, url=url)
        non_resolvable_dates = [x.not_resolvable_since for x in non_resolvable_urls]
        # logger.debug("non_resolvable_dates: %s" % non_resolvable_dates)
    except ObjectDoesNotExist:
        # no non-resolvable urls
        pass

    datetimes = set(
        tls_qualys_scan_dates + generic_scan_dates + non_resolvable_dates + dead_scan_dates)

    # reduce this to one moment per day only, otherwise there will be a report for every change
    # which is highly inefficient.
    # ^ it should be different every time. So, this doesn't matter.
    # for every scan: that is highly inefficient.
    # logger.debug("Amount of dates: %s. Optimizing...", len(datetimes))

    # take the last moment of the date, so the scan will have happened at the correct time
    datetimes2 = [x.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)
                  for x in datetimes]
    datetimes2 = list(set(datetimes2))
    datetimes2.sort()

    # if the last datetime2 is today, then just reduce it to NOW to cause less confusion in
    # the dataset (don't place ratings in the future).
    if not datetimes2:
        return []

    if datetimes2[len(datetimes2) - 1] == datetime.now().replace(
            hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc):
        datetimes2[len(datetimes2) - 1] = datetime.now(pytz.utc)

    logger.debug("Found amount of dates: %s", len(datetimes2))
    # logger.debug("Relevant dates for organization/url: %s", datetimes2)

    timeline = {}

    # reduce to date, it's not useful to show 100 things on a day when building history.
    for time in datetimes2:
        timeline[time.date()] = {}
        timeline[time.date()]["endpoints"] = []
        timeline[time.date()]["ratings"] = []
        timeline[time.date()]["dead_endpoints"] = []

        # only have one ipv4 and opne ipv6 endpoint per moment.
        # this is the one from generic scans, which immediately resolves.
        timeline[time.date()]['had_ipv4'] = {}
        timeline[time.date()]['had_ipv6'] = {}
    # print(timeline)

    # todo: clean dataset and remove useless ratings that won't die.
    # sometimes there have been scans on dead endpoints. This is a problem in the database.
    # this code is correct with retrieving those endpoints again.
    # we could save a list of dead endpoints, but the catch is that an endpoint can start living
    # again over time. The scans with only dead endpoints should not be made.
    for scan_date in generic_scan_dates:
        scan_date = scan_date.date()
        timeline[scan_date]["generic_scan"] = {}
        timeline[scan_date]["generic_scan"]["scanned"] = True
        # prevent a query, below query could be rewritten, which is faster
        # ratings = generic_scans.filter(rating_determined_on__date=scan_date)
        ratings = [x for x in generic_scans if x.rating_determined_on.date() == scan_date]
        timeline[scan_date]["generic_scan"]["ratings"] = list(ratings)
        endpoints = [x.endpoint for x in ratings]
        timeline[scan_date]["generic_scan"]["endpoints"] = endpoints
        for endpoint in endpoints:
            if endpoint not in timeline[scan_date]["endpoints"]:
                timeline[scan_date]["endpoints"].append(endpoint)
        timeline[scan_date]["ratings"] += list(ratings)

    for scan_date in tls_qualys_scan_dates:
        scan_date = scan_date.date()

        timeline[scan_date]["tls_qualys_scan"] = {}
        timeline[scan_date]["tls_qualys_scan"]["scanned"] = True
        # prevent a query, below query could be rewritten, which is faster
        # ratings = list(tls_qualys_scans.filter(rating_determined_on__date=scan_date))
        ratings = [x for x in tls_qualys_scans if x.rating_determined_on.date() == scan_date]
        timeline[scan_date]["tls_qualys_scan"]["ratings"] = ratings
        endpoints = [x.endpoint for x in ratings]
        timeline[scan_date]["tls_qualys_scan"]["endpoints"] = endpoints

        # qualys can deliver multiple IPv4 and IPv6 endpoints. This distorts the scores.
        # What we can do is have only one endpoint for either ipv4 or ipv6.
        # so we first try to match op these endpoints. If it appears there are no matches
        # then you add an ipv4 and 6 endpoint from this set, so no ratings go lost. Some hosts
        # Change IP every five minutes.
        for endpoint in endpoints:
            if endpoint not in timeline[scan_date]["endpoints"]:
                timeline[scan_date]["endpoints"].append(endpoint)
        # timeline[scan_date]["endpoints"] += list(endpoints)
        timeline[scan_date]["ratings"] += list(ratings)

    for scan_date in non_resolvable_dates:
        scan_date = scan_date.date()
        timeline[scan_date]["not_resolvable"] = True

    for scan_date in dead_scan_dates:
        scan_date = scan_date.date()
        timeline[scan_date]["dead"] = True
        # figure out what endpoints died this moment
        for ep in dead_scans:
            if ep.is_dead_since.date() == scan_date:
                if ep not in timeline[scan_date]["dead_endpoints"]:
                    timeline[scan_date]["dead_endpoints"].append(ep)

    # unique endpoints only.
    for time in datetimes2:
        timeline[time.date()]["endpoints"] = list(set(timeline[time.date()]["endpoints"]))

    return timeline


def rate_timeline(timeline, url):
    logger.info("Rebuilding ratings for for %s" % url)

    # will be filled with dates and
    url_rating_jsons = {}

    previous_ratings = {}
    previous_endpoints = []
    for moment in timeline:
        scores = []
        given_ratings = {}

        if 'not_resolvable' in timeline[moment].keys():
            logger.debug('Url became non-resolvable. Adding an empty rating to lower the score of'
                         'this domain if it had a score. It has been cleaned up. (hooray)')
            # this is the end for the domain.
            default_calculation = """
            {"url":
                {
                "url": "%s",
                "points": "0",
                "endpoints": []
                }
            }""" % url.url
            save_url_rating(url, moment, 0, default_calculation)
            return

        # reverse the relation: so we know all ratings per endpoint.
        # It is not really relevant what endpoints _really_ exist.
        endpoint_ratings = {}
        for rating in timeline[moment]['ratings']:
            endpoint_ratings[rating.endpoint.id] = []

        for rating in timeline[moment]['ratings']:
            endpoint_ratings[rating.endpoint.id].append(rating)

        # create the report for this moment
        endpoint_jsons = []

        # also include all endpoints from the past time, which we do until the endpoints are dead.
        relevant_endpoints = set(timeline[moment]["endpoints"] + previous_endpoints)

        # print(relevant_endpoints)
        # print(endpoint_ratings)

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

        # only rate one ipv4 and one ipv6 endpoint: dns either translates to ipv6 or v4.
        # only qualys resolves multiple ipv6 addresses: a normal browser will land on any but just
        # one of them.

        #
        # ratings are duplicated in the database, on multiple endpoints. Should we drop all those
        # extra endpoints (aka: ignore the IP adresses?)

        for endpoint in relevant_endpoints:
            # Don't punish for having multiple IPv4 or IPv6 endpoints: since we visit the site
            # over DNS, there are only two entrypoints: an ipv4 and ipv6 ip.

            ratings = []
            these_ratings = {}
            if endpoint.id in endpoint_ratings.keys():
                for rating in endpoint_ratings[endpoint.id]:
                    if type(rating) == TlsQualysScan:
                        these_ratings['tls_qualys_scan'] = rating
                    if type(rating) == EndpointGenericScan:
                        if rating.type == 'Strict-Transport-Security':
                            these_ratings['Strict-Transport-Security'] = rating
                    if type(rating) == EndpointGenericScan:
                        if rating.type == 'X-Content-Type-Options':
                            these_ratings['X-Content-Type-Options'] = rating
                    if type(rating) == EndpointGenericScan:
                        if rating.type == 'X-Frame-Options':
                            these_ratings['X-Frame-Options'] = rating
                    if type(rating) == EndpointGenericScan:
                        if rating.type == 'X-XSS-Protection':
                            these_ratings['X-XSS-Protection'] = rating
                    if type(rating) == EndpointGenericScan:
                        if rating.type == 'plain_https':
                            these_ratings['plain_https'] = rating

            # enrich the ratings with previous ratings, without overwriting them.
            if "tls_qualys_scan" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "tls_qualys_scan" in previous_ratings[endpoint.id].keys():
                        these_ratings['tls_qualys_scan'] = previous_ratings[endpoint.id]['tls_qualys_scan']

            if "Strict-Transport-Security" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "Strict-Transport-Security" in previous_ratings[endpoint.id].keys():
                        these_ratings['Strict-Transport-Security'] = \
                            previous_ratings[endpoint.id]['Strict-Transport-Security']

            if "X-Content-Type-Options" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "X-Content-Type-Options" in previous_ratings[endpoint.id].keys():
                        these_ratings['X-Content-Type-Options'] = \
                            previous_ratings[endpoint.id]['X-Content-Type-Options']

            if "X-Frame-Options" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "X-Frame-Options" in previous_ratings[endpoint.id].keys():
                        these_ratings['X-Frame-Options'] = \
                            previous_ratings[endpoint.id]['X-Frame-Options']

            if "X-XSS-Protection" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "X-XSS-Protection" in previous_ratings[endpoint.id].keys():
                        these_ratings['X-XSS-Protection'] = \
                            previous_ratings[endpoint.id]['X-XSS-Protection']

            if "plain_https" not in these_ratings.keys():
                if endpoint.id in previous_ratings.keys():
                    if "plain_https" in previous_ratings[endpoint.id].keys():
                        these_ratings['plain_https'] = previous_ratings[endpoint.id]['plain_https']

            # propagate the ratings to the next iteration.
            previous_ratings[endpoint.id] = {}
            previous_ratings[endpoint.id] = these_ratings

            # build the json:
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

            message = "Repeated finding. Probably because this url changed IP adresses or has multiple IP " \
                      "adresses (common for failover / load-balancing)."

            repetition_message = """{
                        "type": "%s",
                        "explanation": "%s",
                        "points": 0,
                        "since": "%s",
                        "last_scan": "%s"
                        }
            """
            endpoint_scores = []
            if 'tls_qualys_scan' in these_ratings.keys():
                if 'tls_qualys_scan' not in given_ratings[label]:
                    score, json = tls_qualys_rating_based_on_scan(these_ratings['tls_qualys_scan'])
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('tls_qualys_scan')
                else:
                    ratings.append(repetition_message % (
                        'tls_qualys',
                        message,
                        these_ratings['tls_qualys_scan'].rating_determined_on,
                        these_ratings['tls_qualys_scan'].scan_moment,))

            if 'Strict-Transport-Security' in these_ratings.keys():
                if 'Strict-Transport-Security' not in given_ratings[label]:
                    score, json = security_headers_rating_based_on_scan(
                        these_ratings['Strict-Transport-Security'], 'Strict-Transport-Security')
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('Strict-Transport-Security')
                else:
                    ratings.append(repetition_message % (
                        'security_headers_strict_transport_security',
                        message,
                        these_ratings['Strict-Transport-Security'].rating_determined_on,
                        these_ratings['Strict-Transport-Security'].last_scan_moment,))

            if 'X-Frame-Options' in these_ratings.keys():
                if 'X-Frame-Options' not in given_ratings[label]:
                    score, json = security_headers_rating_based_on_scan(
                        these_ratings['X-Frame-Options'], 'X-Frame-Options')
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('X-Frame-Options')
                else:
                    ratings.append(repetition_message % (
                        'security_headers_x_frame_options',
                        message,
                        these_ratings['X-Frame-Options'].rating_determined_on,
                        these_ratings['X-Frame-Options'].last_scan_moment,))

            if 'X-XSS-Protection' in these_ratings.keys():
                if 'X-XSS-Protection' not in given_ratings[label]:
                    score, json = security_headers_rating_based_on_scan(
                        these_ratings['X-XSS-Protection'], 'X-XSS-Protection')
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('X-XSS-Protection')
                else:
                    ratings.append(repetition_message % (
                        'security_headers_x_xss_protection',
                        message,
                        these_ratings['X-XSS-Protection'].rating_determined_on,
                        these_ratings['X-XSS-Protection'].last_scan_moment,))

            if 'X-Content-Type-Options' in these_ratings.keys():
                if 'X-Content-Type-Options' not in given_ratings[label]:
                    score, json = security_headers_rating_based_on_scan(
                        these_ratings['X-Content-Type-Options'], 'X-Content-Type-Options')
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('X-Content-Type-Options')
                else:
                    ratings.append(repetition_message % (
                        'security_headers_x_content_type_options',
                        message,
                        these_ratings['X-Content-Type-Options'].rating_determined_on,
                        these_ratings['X-Content-Type-Options'].last_scan_moment,))

            if 'plain_https' in these_ratings.keys():
                if 'plain_https' not in given_ratings[label]:
                    score, json = http_plain_rating_based_on_scan(these_ratings['plain_https'])
                    ratings.append(json) if json else ""
                    scores.append(score)
                    endpoint_scores.append(score)
                    given_ratings[label].append('plain_https')
                else:
                    ratings.append(repetition_message % (
                        'plain_https',
                        message,
                        these_ratings['plain_https'].rating_determined_on,
                        these_ratings['plain_https'].last_scan_moment,))

            # todo: remove the unneeded endpoint label.
            endpoint_template = """
        {
            "ip": "%s",
            "port": "%s",
            "protocol": "%s",
            "v4": "%s",
            "points": %s,
            "ratings": [%s]

        }""".strip()

            # this makes the whole operation a bit slower, but more readable, which matters.
            # is also verified json. That also helps.
            # print(ratings)
            # print(",".join(jsons))
            unsorted = xjson.loads("[" + ",".join(ratings) + "]")
            # unsorted.sort(key)
            sorted_ratings = sorted(unsorted, key=lambda k: k['points'], reverse=True)

            # without correct indent, you'll get single quotes
            sorted_ratings = xjson.dumps(obj=sorted_ratings, indent=4)

            if sorted_ratings[0:1] == "[":
                sorted_ratings = sorted_ratings[1:len(sorted_ratings) - 1]  # we add [] somewhere else already.

            # there is difference between these objects, it seems.
            # print("l")
            # print(l)
            # print("z")

            endpoint_jsons.append(endpoint_template % (endpoint.ip,
                                                       endpoint.port,
                                                       endpoint.protocol,
                                                       endpoint.is_ipv4(),
                                                       sum(endpoint_scores),
                                                       sorted_ratings))

        previous_endpoints += relevant_endpoints
        url_rating_template = """
    {
        "url": "%s",
        "points": %s,
        "endpoints": [%s]
    }""".strip()

        # prevent empty ratings cluttering the database and skewing the stats.
        if not endpoint_jsons:
            continue

        # print(endpoint_jsons)
        # todo sort endpoints. with the same disgusting code :)
        unsorted = xjson.loads("[" + ",".join(endpoint_jsons) + "]")
        sorted_endpoints = sorted(unsorted, key=lambda k: k['points'], reverse=True)
        sorted_endpoints = xjson.dumps(obj=sorted_endpoints, indent=4)
        if sorted_endpoints[0:1] == "[":
            sorted_endpoints = sorted_endpoints[1:len(sorted_endpoints) - 1]  # we add [] somewhere else already.

        url_rating_json = url_rating_template % (url.url, sum(scores), sorted_endpoints)
        logger.debug("On %s this would score: %s " % (moment, sum(scores)), )
        # logger.debug("With JSON: %s " % ",".join(endpoint_jsons))
        # logger.debug("Url rating json: %s", url_rating_json)
        # import json as blaat
        # parsed = blaat.loads(url_rating_json)

        save_url_rating(url, moment, sum(scores), url_rating_json)


def save_url_rating(url, date, score, json):
    u = UrlRating()
    u.url = url

    # save it as NOW if it's done today, else on the last moment on the same day.
    # So the url ratings immediately are shown, even if the day is not over.

    if date == datetime.now().date():
        u.when = datetime.now(pytz.utc)
    else:
        u.when = datetime(year=date.year, month=date.month, day=date.day,
                      hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)
    u.rating = score
    u.calculation = json
    u.save()


def show_timeline_console(timeline, url):
    print("")
    print(url.url)
    for moment in timeline:
        scores = []
        # prepare endpoints to contain ratings
        # for ep in timeline[moment]['endpoints']:
        #     ep["ratings"] = {}
        print("|")
        print("|- %s: %s" % (moment, timeline[moment].keys()))
        # print ("|  |")
        if 'tls_qualys_scan' in timeline[moment].keys():
            print("|  |- tls_qualys_scan")
            for item in timeline[moment]['tls_qualys_scan']['endpoints']:
                print("|  |  |- Endpoint %s" % item)
            for item in timeline[moment]['tls_qualys_scan']['ratings']:
                score, json = tls_qualys_rating_based_on_scan(item)
                print("|  |  |- %s points: %s" % (score, item))

        # These are all generic scans, left here to debug your timeline.
        # if 'generic_scan' in timeline[time].keys():
        #     print ("|  |- generic_scan")
        #     for item in timeline[time]['generic_scan']['ratings']:
        #         print ("|  |  |- %s" % item)

        # generic scans have a lot of subtypes.
        if 'generic_scan' in timeline[moment].keys():
            print("|  |- generic_scan")
            for item in timeline[moment]['generic_scan']['ratings']:
                if item.type == "plain_https":
                    score, json = http_plain_rating_based_on_scan(item)
                    print("|  |  |- %s points: %s" % (score, item))
            for item in timeline[moment]['generic_scan']['ratings']:
                if item.type == "Strict-Transport-Security":
                    score, json = security_headers_rating_based_on_scan(item, "Strict-Transport-Security")
                    print("|  |  |- %s points: %s" % (score, item))
            for item in timeline[moment]['generic_scan']['ratings']:
                if item.type == "X-Frame-Options":
                    score, json = security_headers_rating_based_on_scan(item, "X-Frame-Options")
                    print("|  |  |- %s points: %s" % (score, item))
            for item in timeline[moment]['generic_scan']['ratings']:
                if item.type == "X-Content-Type-Options":
                    score, json = security_headers_rating_based_on_scan(item, "X-Content-Type-Options")
                    print("|  |  |- %s points: %s" % (score, item))
            for item in timeline[moment]['generic_scan']['ratings']:
                if item.type == "X-XSS-Protection":
                    score, json = security_headers_rating_based_on_scan(item, "X-XSS-Protection")
                    print("|  |  |- %s points: %s" % (score, item))

        if 'dead' in timeline[moment].keys():
            print("|  |- dead endpoints")
            for endpoint in timeline[moment]['dead_endpoints']:
                print("|  |  |- %s" % endpoint)

        if 'not_resolvable' in timeline[moment].keys():
            print("|  |- url became not resolvable")

    print("")


def significant_times(organization=None, url=None):
    """
    Searches for all significant point in times that something changed. The goal is to save
    unneeded queries when rebuilding ratings. When you know when things changed, you know
    at what moments you need to create reports.

    Another benefit is not only less queries, but also more granularity for reporting: not just
    per week, but known per day.

    We want to know:
    - When a rating was made, since only changes are saved, all those datapoints.
    - - This implies when the url was alive (at least after a positive result).
    - When a url was not resolvable (aka: is not in the report anymore)

    :return:
    """

    # todo: all this validation adds to complexity.
    if organization and url:
        logger.info("Both URL and organization given, please supply one! %s %s" %
                    (organization, url))
        return []

    urls = []
    if organization:
        logger.info("Getting all urls from organization: %s" % organization)
        urls = Url.objects.filter(organization=organization)
    if url:
        logger.info("Getting all url: %s" % url)
        urls = [url]

    if not urls:
        logger.info("Could not find urls from organization or url.")
        return []

    tls_qualys_scan_dates = []
    try:
        tls_qualys_scans = TlsQualysScan.objects.all().filter(endpoint__url__in=urls)
        tls_qualys_scan_dates = [x.rating_determined_on for x in tls_qualys_scans]
        logger.debug("tls_qualys_scan_dates: %s" % tls_qualys_scan_dates)
    except ObjectDoesNotExist:
        # no tls scans
        pass

    generic_scan_dates = []
    try:
        generic_scans = EndpointGenericScan.objects.all().filter(endpoint__url__in=urls)
        generic_scan_dates = [x.rating_determined_on for x in generic_scans]
        logger.debug("generic_scan_dates: %s" % generic_scan_dates)
    except ObjectDoesNotExist:
        # no generic scans
        pass

    dead_scan_dates = []
    try:
        dead_scans = Endpoint.objects.all().filter(url__in=urls, is_dead=True)
        dead_scan_dates = [x.is_dead_since for x in dead_scans]
        logger.debug("dead_scan_dates: %s" % dead_scan_dates)
    except ObjectDoesNotExist:
        # no generic scans
        pass

    # is this relevant? I think we can do without.
    non_resolvable_dates = []
    try:
        non_resolvable_urls = Url.objects.filter(not_resolvable=True,
                                                 is_dead=False,
                                                 url__in=urls)
        non_resolvable_dates = [x.not_resolvable_since for x in non_resolvable_urls]
        logger.debug("non_resolvable_dates: %s" % non_resolvable_dates)
    except ObjectDoesNotExist:
        # no non-resolvable urls
        pass

    datetimes = set(
        tls_qualys_scan_dates + generic_scan_dates + non_resolvable_dates + dead_scan_dates)

    # reduce this to one moment per day only, otherwise there will be a report for every change
    # which is highly inefficient.
    # todo: the order of this list should be chronological: otherwise ratings get overwritten?
    # ^ it should be different every time. So, this doesn't matter.
    # for every scan: that is highly inefficient.
    logger.debug("Found amount of dates, optimizing: %s", len(datetimes))

    # take the last moment of the date, so the scan will have happened at the correct time
    datetimes2 = [x.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc)
                  for x in datetimes]
    datetimes2 = list(set(datetimes2))
    datetimes2.sort()

    # if the last datetime2 is today, then just reduce it to NOW to cause less confusion in
    # the dataset (don't place ratings in the future).
    if datetimes2:
        if datetimes2[len(datetimes2) - 1] == datetime.now().replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc):
            datetimes2[len(datetimes2) - 1] = datetime.now(pytz.utc)

        logger.debug("Found amount of dates: %s", len(datetimes2))
        # logger.debug("Relevant dates for organization/url: %s", datetimes2)

    return datetimes2


# also callable as admin action
# this is 100% based on url ratings, just an aggregate of the last status.
# make sure the URL ratings are up to date, they will check endpoints and such.


# probably not used anymore
# def rate_organizations(organizations, when=""):
#     # since a url can now have multiple organizations, you should rate each one separately
#     for organization in organizations.all():
#         rate_organization(organization, when)


def rate_organization(organization, when=""):
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    logger.debug("rating on: %s, Organization %s" % (when, organization))

    total_rating = 0

    # todo: closing off urls, after no relevant endpoints, but still resolvable.
    urls = get_relevant_urls_at_timepoint(organization=organization,
                                          when=when)
    all_url_ratings = []
    calculation_json = []
    for url in urls:
        try:
            urlratings = UrlRating.objects.filter(url=url, when__lte=when)
            urlratings = urlratings.values("rating", "calculation")
            urlrating = urlratings.latest("when")  # kills the queryset, results 1
            all_url_ratings.append(urlrating)
        except UrlRating.DoesNotExist:
            logger.warning("Url has no rating at this moment: %s %s" % (url, when))
            pass

    # sort all_url_ratings on rating desc.
    # https://stackoverflow.com/questions/403421/
    all_url_ratings.sort(key=lambda x: x['rating'], reverse=True)

    for urlrating in all_url_ratings:
        total_rating += urlrating["rating"]
        calculation_json.append(urlrating["calculation"])

    try:
        last = OrganizationRating.objects.filter(
            organization=organization, when__lte=when).latest('when')
    except OrganizationRating.DoesNotExist:
        logger.debug("Could not find the last organization rating, creating a dummy one.")
        last = OrganizationRating()  # create an empty one

    # A rating of 0 is desired.
    # rated on will add a new organizationrating every time. It's very useful for debugging
    # and showing when ratings happened.

    organizationratingtemplate = """
{
"organization": {
    "name": "%s",
    "rating": "%s",
    "urls": [%s]
    }
}""".strip()

    organization_json = (organizationratingtemplate % (organization.name, total_rating,
                                                       ",".join(calculation_json)))
    # print(organization_json)
    # verify the JSON is correct
    # parsed = json.loads(organization_json)
    # organization_json_checked = json.dumps(parsed)
    # print("%s %s" % (last.calculation, total_calculation))
    if last.calculation != organization_json:
        logger.debug("The calculation (json) has changed, so we're saving this report, rating.")
        u = OrganizationRating()
        u.organization = organization
        u.rating = total_rating
        u.when = when
        u.calculation = organization_json
        u.save()
    else:
        logger.warning(
            "The calculation is still the same, not creating a new OrganizationRating")


# also callable as admin action
# this is incomplete, use the timeline variant -> it's better with endpoints over time.
# but this will give the correct score, possibly on the wrong endpoints.
def rate_url(url, when=""):
    if not when:
        when = datetime.now(pytz.utc)

    # contains since, last scan, rating, reason rating was given.
    explanation, rating = get_url_score_modular(url, when)

    # it's very possible there is no rating yet
    # we do show the not_resolvable history.
    try:
        last_url_rating = \
            UrlRating.objects.filter(url=url,
                                     url__urlrating__when__lte=when,
                                     url__is_dead=False).latest("when")
    except ObjectDoesNotExist:
        # make sure there is no exception later on.
        last_url_rating = UrlRating()  # todo: evaluate if this is a wise approach.

    # avoid duplication. We think the explanation is the most unique identifier.
    # therefore the order in which URLs are grabbed (if there are new ones) is important.
    # it cannot be random, otherwise the explanation will be different every time.
    if explanation and last_url_rating.calculation != explanation:
        u = UrlRating()
        u.url = url
        u.rating = rating
        u.when = when
        u.calculation = explanation
        u.save()
    else:
        logger.warning("The calculation is still the same, not creating a new UrlRating")


"""
from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Url, Organization
u = Url.objects.all().filter(url="loket.zaanstad.nl").get()
get_url_score_modular(u)
rate_url(u)
o = Organization.objects.all().filter(name="Zaanstad").get()
rate_organization(o)
"""


def get_url_score_modular(url, when=""):
    if not when:
        when = datetime.now(pytz.utc)

    logger.debug("Calculating url score for %s on %s" % (url.url, when))

    """
    A relevant endpoint is an endpoint that is still alive or was alive at the time.
    Due to being alive (or at the time) it can get scores from various scanners more easily.

    Afterwards we'll check if at this time there also where dead endpoints.
    Dead endpoints add 0 points to the rating, but it can lower a rating.(?)
    """
    endpoints = get_relevant_endpoints_at_timepoint(url, when)

    # sometimes you'll get a series of ipv6 and ipv4 endpoints. These are often used for load
    # balancing. Many SIP domains have 6 ipv6 endpoints, and amsterdam uses 2xipv4 and 2xipv6.
    # For an end-user it doesn't really matter that there are a gazillion ip addresses behin
    # the loadbalancer. It can either enter through ipv4 or ipv6 (due dns resolution).
    # therefore: we'll only rate maximum 1 ipv4 and one ipv6 endpoint. The rest will be added
    # to the report, but will not be given a rating.
    # It would be strange if one address has different content than the other, while possible.
    had_ipv4 = False
    had_ipv6 = False

    # general reporting json:
    url_rating_template = """
    {
    "url": {
        "url": "%s",
        "points": "%s",
        "endpoints": [%s]
        }
    }""".strip()

    endpoint_template = """
        {
        "%s:%s": {
            "ip": "%s",
            "port": "%s",
            "protocol": "%s",
            "ratings": [%s]
            }
        }""".strip()

    rating = 0
    endpoint_jsons = []
    for endpoint in endpoints:

        # todo: add some empty rating, to still show the endpoint in the report.
        # this only works when all endpoints are equally rated, which has always been the case
        if had_ipv4 and endpoint.is_ipv4():
            continue

        if had_ipv6 and endpoint.is_ipv6():
            continue

        if endpoint.is_ipv6():
            had_ipv6 = True
        else:
            had_ipv4 = True

        (scanner_tls_qualys_rating, scanner_tls_qualys_json) = \
            get_report_from_scanner_tls_qualys(endpoint, when)

        (scanner_http_plain_rating, scanner_http_plain_json) = \
            get_report_from_scanner_http_plain(endpoint, when)

        (r1, j1) = get_report_from_scanner_security_headers(endpoint, when,
                                                            'Strict-Transport-Security')

        (r2, j2) = get_report_from_scanner_security_headers(endpoint, when,
                                                            'X-Content-Type-Options')

        (r3, j3) = get_report_from_scanner_security_headers(endpoint, when,
                                                            'X-Frame-Options')

        (r4, j4) = get_report_from_scanner_security_headers(endpoint, when,
                                                            'X-XSS-Protection')

        jsons = []
        jsons.append(scanner_tls_qualys_json) if scanner_tls_qualys_json else ""
        jsons.append(scanner_http_plain_json) if scanner_http_plain_json else ""
        jsons.append(j1) if j1 else ""
        jsons.append(j2) if j2 else ""
        jsons.append(j3) if j3 else ""
        jsons.append(j4) if j4 else ""

        rating += int(scanner_tls_qualys_rating) + int(scanner_http_plain_rating) + \
            int(r1) + int(r2) + int(r3) + int(r4)

        if jsons:
            endpoint_jsons.append((endpoint_template % (endpoint.ip,
                                                        endpoint.port,
                                                        endpoint.ip,
                                                        endpoint.port,
                                                        endpoint.protocol,
                                                        ",".join(jsons))))
        else:
            logger.debug('No tls or http rating at this moment. Not saving. %s %s' %
                         (url, when))

    if not endpoints:
        logger.error('No relevant endpoints at this time, probably didnt exist yet. %s %s' %
                     (url, when))
        close_url_rating(url, when)
    # Don't do this. While it's better somewhere, we now at generating check
    # if there is still an endpoint that we should include. Perhaps at a rewrite
    # add a "it's empty now" as latest rating. The reason for not doing this now
    # is that it will have a zero rating, and all scans will end on a zero rating after cleanup
    # and you will then report way too much endpoints. - hard to explain.
    #
    # Now there may be a set of two endpoints: one is dead, one is alive.
    # We want to make sure that dead endpoints are included as the url rating
    # given we want to get the latest state. A dead endpoint most likely will reduce
    # the rating. If the endpoint was
    # if False:
    #     (scanner_dead_rating, scanner_dead_json) = \
    #         get_report_from_scanner_dead(endpoint, when)
    #     jsons.append(scanner_dead_json) if scanner_dead_json else ""
    #     int(scanner_dead_rating)

    # now prepare the url bit:
    if endpoint_jsons:
        url_json = url_rating_template % (url.url, rating, ",".join(endpoint_jsons))
        # logger.debug(url_json)
        # verify correctness of json:
        # parsed = json.loads(url_json)
        # url_json = json.dumps(parsed)  # nice format
        return url_json, rating
    else:
        # empty explanations don't get saved.
        return "", 0


def close_url_rating(url, when):
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

    default_calculation = """
    {"url":
        {
        "url": "%s",
        "points": "0",
        "endpoints": []
        }
    }""" % url.url

    try:
        urlratings = UrlRating.objects.filter(url=url, when__lte=when)
        urlrating = urlratings.latest("when")
        if urlrating.calculation != default_calculation:
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


def get_report_from_scanner_dead(endpoint, when):
    logger.debug("get_report_from_scanner_dead")
    """
    Endpoints also die. In that case, you do return a rating of 0 for that endpoint.

    So that when you get the latest URL rating, you'll get 0 points, instead of some old
    score. If the endpoint is dead, well: it has been cleaned up. Which is a good thing mostly.

    Endpoints have the lifecycle: once dead, it stays dead. A new endpoint will be created when
    a new scan is performed. The new endpoint may be exactly the same as the old one, including
    IP and such. This might be a bit confusing.
    """

    rating_template = """
            {
            "dead": {
                "explanation": "%s",
                "points": 0,
                "since": "%s",
                "last_scan": "%s"
                }
            }""".strip()

    try:
        scan = Endpoint.objects.filter(id=endpoint.id,
                                       is_dead_since__lte=when,
                                       )
        scan = scan.latest('is_dead_since')

        json = (rating_template % ("Endpoint was cleaned up.",
                                   scan.is_dead_since, scan.is_dead_since))

        logger.debug("Dead: On %s, Endpoint %s was dead." % (when, endpoint))
        return 0, json
    except ObjectDoesNotExist:
        logger.debug("Endpoint is not dead: %s." % endpoint)
        return 0, ""


def security_headers_rating_based_on_scan(scan, header='Strict-Transport-Security'):
    security_headers_scores = {
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
        # prevents reflected xss
        'X-XSS-Protection': 100,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
        # prevents clickjacking
        'X-Frame-Options': 200,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options
        # forces the content-type to be leading for defining a type of file (not the browser guess)
        # The browser guess could execute the file, for example with the wrong plugin.
        # Basically the server admin should fix the browser, instead of the other way around.
        'X-Content-Type-Options': 25,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
        # Will be the browser default. Forces https, even if http resources are available.
        #
        # The preload list is idiotic: it should contain any site in the world.
        # A whopping 1 municipality in NL uses the preload list (eg knows if it's existence).
        # preload list is obscure and a dirty fix for a structural problem.
        #
        # Another weird thing is: the default / recommendation for hsts is off. Many sites, esp. in
        # governments have a once-a-year cycle for doing something requires. So HSTS should be
        # longer than a year, like one year and three months. Some site punish long hsts times.
        'Strict-Transport-Security': 200,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Public-Key-Pins
        # Has the potential to make your site unreachable if not properly (automatically) maintained
        # The backup cert strategy is also incredibly complex. Creating the right hash is also hard.
        # So if you don't use this. There should be another way to link the content of the site to
        # the transport.
        # header likely to be killed like p3p
        'Public-Key-Pins': 0,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
        # Very complex header to specify what resources can be loaded from where. Especially useful
        # when loading in third party content such as horrible ads. Prevents against xss
        'Content-Security-Policy': 50,

        # Flash, PDF and other exploit prone things can be embedded. Should never happen:
        # the content should always be none(?).
        # if not set to none, it is 200 points for allowing flash and pdf to be embedded at all :)
        'X-Permitted-Cross-Domain-Policies': 25,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy
        # largely unsupported
        # What referrer should be allowed to access the resource. Security on referrer headers? No.
        'Referrer-Policy': 0
    }

    rating_template = """
                {
                    "type": "security_headers_%s",
                    "explanation": "%s",
                    "points": %s,
                    "since": "%s",
                    "last_scan": "%s"
                }""".strip()

    # don't need to add things that are OK to the report. It might be in the future.
    if scan.rating == "True":
        json = (rating_template % (
            header.lower().replace("-", "_"),
            header + " header present.",
            0,
            scan.rating_determined_on,
            scan.last_scan_moment))
        rating = 0

    else:
        json = (rating_template % (
            header.lower().replace("-", "_"),
            "Missing " + header + " header.",
            security_headers_scores[scan.type],
            scan.rating_determined_on,
            scan.last_scan_moment))
        rating = security_headers_scores[scan.type]

    return rating, json


# todo: this should take multiple generic scans on headers.
# todo: this misses in score rating modular
def get_report_from_scanner_security_headers(endpoint, when, header):
    try:
        # also here: the last scan moment increases with every scan. When you have a set of
        # relevant dates (when scans where made) ....
        scan = EndpointGenericScan.objects.filter(endpoint=endpoint,
                                                  rating_determined_on__lte=when,
                                                  type=header,
                                                  )
        scan = scan.latest('rating_determined_on')

        rating, json = security_headers_rating_based_on_scan(scan, header)

        logger.debug("security_headers: On %s, Endpoint %s, Rated %s" %
                     (when, endpoint, rating))
        return rating, json
    except ObjectDoesNotExist:
        logger.debug("No security_headers on endpoint %s." % endpoint)
        return 0, ""


def get_report_from_scanner_http_plain(endpoint, when):
    logger.debug("get_report_from_scanner_http_plain")

    if endpoint.protocol != "http":
        logger.debug("Endpoint is not on the right protocol. Nothing to find.")
        return 0, ""

    try:
        # also here: the last scan moment increases with every scan. When you have a set of
        # relevant dates (when scans where made) ....
        scan = EndpointGenericScan.objects.filter(endpoint=endpoint,
                                                  rating_determined_on__lte=when,
                                                  type="plain_https",
                                                  )
        scan = scan.latest('rating_determined_on')

        rating, json = http_plain_rating_based_on_scan(scan)

        logger.debug("plain_https: On %s, Endpoint %s, Rated %s" %
                     (when, endpoint, rating))
        return rating, json
    except ObjectDoesNotExist:
        logger.debug("No http plain scan on endpoint %s." % endpoint)
        return 0, ""


def http_plain_rating_based_on_scan(scan):
    rating_template = """
                    {
                        "type": "plain_https",
                        "explanation": "%s",
                        "points": %s,
                        "since": "%s",
                        "last_scan": "%s"
                    }""".strip()

    # changed the ratings in the database. They are not really correct.
    # When there is no https at all, it's worse than having broken https. So rate them the same.
    if scan.explanation == "Site does not redirect to secure url, and has nosecure alternative on a standard port.":
        scan.rating = 1000

    # And have redirects looked at: why is there no secure alternative on the standard counterpart port?
    if scan.explanation == "Redirects to a secure site, while a secure counterpart on the standard port is missing.":
        scan.rating = 200

    # also here: the last scan moment increases with every scan. When you have a set of
    # relevant dates (when scans where made) ....

    json = (rating_template % (scan.explanation,
                               scan.rating,
                               scan.rating_determined_on,
                               scan.last_scan_moment))
    return int(scan.rating), json


def get_report_from_scanner_tls_qualys(endpoint, when):
    try:
        # the last scan moment always increases. If you would select on scan_moment,
        # the scan moment can be way in the future. It should be the date the rating is
        # determined on.
        # scan = TlsQualysScan.objects.filter(endpoint=endpoint, scan_moment__lte=when)
        scan = TlsQualysScan.objects.filter(endpoint=endpoint, rating_determined_on__lte=when)
        scan = scan.latest('rating_determined_on')
        rating, starttls_json = tls_qualys_rating_based_on_scan(scan)
        logger.debug("TLS: On %s, Endpoint %s, Rated %s" % (when, endpoint, rating))
        if starttls_json:
            return rating, starttls_json
        else:
            logger.debug("TLS: This tls scan resulted in no https. Not returning a score.")
            return 0, ""
    except TlsQualysScan.DoesNotExist:
        # can happen that a rating simply isn't there yet. Perfectly possible.
        logger.debug("No tls qualys scan on endpoint %s." % endpoint)
        pass

    return 0, ""


def tls_qualys_rating_based_on_scan(scan):
    """
    Qualys gets multiple endpoints
    :param endpoint:
    :param when:
    :return:
    """
    explanations = {
        "F": "Broken Transport Security, rated F",
        "D": "Nearly broken Transport Security, rated D",
        "C": "Less than optimal Transport Security, rated C.",
        "B": "Less than optimal Transport Security, rated B.",
        "A-": "Good Transport Security, rated A-.",
        "A": "Good Transport Security, rated A.",
        "A+": "Perfect Transport Security, rated A+.",
        "T": "Could not establish trust. ",
        "I": "Certificate not valid for domain name.",  # Custom message
        "0": "-",
    }

    # 0? that's port 443 without using TLS. That is extremely rare. In that case...
    # 0 is many cases a "not connect to server" error currently. But there is more.
    # Now checking messages returned from qualys. Certificate invalid for domain name now
    # is awarded points.
    ratings = {"T": 200,
               "F": 1000,
               "D": 400,
               "I": 200,
               "C": 100,
               "B": 50,
               "A-": 0,
               "A": 0,
               "A+": 0,
               "0": 0}

    tlsratingtemplate = """
            {
                    "type": "tls_qualys",
                    "explanation": "%s",
                    "points": %s,
                    "since": "%s",
                    "last_scan": "%s"
                }""".strip()

    # configuration errors
    if scan.qualys_message == "Certificate not valid for domain name":
        scan.qualys_rating = "I"

    if scan.qualys_rating != '0':
        if scan.qualys_rating == "T":
            rating = ratings[scan.qualys_rating] + ratings[scan.qualys_rating_no_trust]
            explanation = explanations[scan.qualys_rating] + \
                " For the certificate installation: " + \
                explanations[scan.qualys_rating_no_trust]
            starttls_json = (tlsratingtemplate %
                             (explanation, rating,
                              scan.rating_determined_on, scan.scan_moment))
        else:
            starttls_json = (tlsratingtemplate %
                             (explanations[scan.qualys_rating], ratings[scan.qualys_rating],
                              scan.rating_determined_on, scan.scan_moment))

            rating = ratings[scan.qualys_rating]

        return rating, starttls_json
    else:
        logger.debug("TLS: This tls scan resulted in no https. Not returning a score.")
        return 0, ""


def get_relevant_urls_at_timepoint(organization, when):
    """
    It's possible that the url only has endpoints that are dead, but the URL resolves fine.

    :param organization:
    :param when:
    :return:
    """

    urls = Url.objects.filter(organization=organization)

    # urls alive at this moment, that are dead in the future
    not_resolving_urls = urls.filter(
        created_on__lte=when,
        not_resolvable=True,
        not_resolvable_since__gte=when,
    )
    logger.debug("Not resolvable urls:  %s" % not_resolving_urls.count())

    dead_urls = urls.filter(
        created_on__lte=when,
        is_dead=True,
        is_dead_since__gte=when,
    )
    logger.debug("Dead urls:  %s" % dead_urls.count())

    # urls that are still alive
    existing_urls = urls.filter(
        created_on__lte=when,
        not_resolvable=False,
        is_dead=False,
    )  # or is_dead=False,
    logger.debug("Alive urls:  %s" % existing_urls.count())

    url_list = list(not_resolving_urls) + list(dead_urls) + list(existing_urls)
    url_list_with_relevant_endpoints = []
    for url in url_list:
        # Check if they also had relevant endpoint. We do this separately to reduce the
        # enormous complexity of history in queries. It's slower, but easier to understand.
        has_endpoints = get_relevant_endpoints_at_timepoint(url=url, when=when)
        if has_endpoints:
            logger.debug(
                "The url %s is relevant on %s and has endpoints: " % (url, when))
            url_list_with_relevant_endpoints.append(url)
        else:
            logger.debug("While the url %s was relevant on %s, "
                         "it does not have any relevant endpoints" % (url, when))

    return url_list_with_relevant_endpoints


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
        r.calculation = """
{
    "organization": {
      "name": "%s",
      "rating": "-1",
      "urls": []
    }
}
        """.strip() % organization.name
        r.save()


# removed port=443, and protocol="https", since we want all types of scans to show.
def get_relevant_endpoints_at_timepoint(url, when):
    endpoints = Endpoint.objects.all()

    # all endpoints in the past given the timeframe, they can be dead.
    then_alive = endpoints.filter(
        url=url,
        discovered_on__lte=when,
        is_dead=True,
        is_dead_since__gte=when,
    )
    logger.debug("Then alive endpoints for this url:  %s" % then_alive.count())

    # all endpoints that are still alive on the timeperiod
    still_alive_endpoints = endpoints.filter(
        url=url,
        discovered_on__lte=when,
        is_dead=False,
    )

    logger.debug("Alive endpoints for this url: %s" % still_alive_endpoints.count())

    endpoint_list = list(then_alive) + list(still_alive_endpoints)

    for endpoint in endpoint_list:
        logger.debug("relevant endpoint for %s: %s" % (when, endpoint))

    return endpoint_list
