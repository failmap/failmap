import json
from datetime import datetime

import pytz
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta  # history
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint, TlsQualysScan

from .models import OrganizationRating, UrlRating
import logging

logger = logging.getLogger(__package__)


class DetermineRatings:
    """
    Here the magic happens for determining a rating for a url and ultimately an organization.

    How we approach this: we first make daily ratings for the last days and store them
        except if it results in the same rating as previous.

    """
    @staticmethod
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

    @staticmethod
    def rate_organizations(create_history=False):
        times = DetermineRatings.get_weekly_intervals() if create_history else [datetime.now(pytz.utc)]

        os = Organization.objects.all()
        for when in times:
            for o in os:
                DetermineRatings.rate_organization(o, when)

    @staticmethod
    def rate_urls(create_history=False):

        times = DetermineRatings.get_weekly_intervals() if create_history else [datetime.now(pytz.utc)]

        urls = Url.objects.filter(is_dead=False)

        for when in times:
            for url in urls:
                DetermineRatings.rate_url(url, when)

    # also callable as admin action
    # this is 100% based on url ratings, just an aggregate of the last status.
    # make sure the URL ratings are up to date, they will check endpoints and such.
    @staticmethod
    def rate_organization(organization, when=""):

        # If there is no time slicing, then it's today.
        if not when:
            when = datetime.now(pytz.utc)

        logger.debug("rating on: %s, Organization %s" % (when, organization))

        total_rating = 0
        total_calculation = ""

        urls = Url.objects.filter(organization=organization, is_dead=False)

        for url in urls:
            try:
                urlratings = UrlRating.objects
                urlratings = urlratings.filter(url=url, when__lte=when)
                urlratings = urlratings.values("rating", "calculation")
                urlrating = urlratings.latest("when")  # kills the queryset, results 1

                # some urls are never rated
                total_rating += urlrating["rating"]

                # when there are multiple urls, add the mandatory comma....
                if total_calculation:
                    total_calculation += ","

                total_calculation += urlrating["calculation"]
            except UrlRating.DoesNotExist:
                pass

        try:
            last = OrganizationRating.objects.filter(
                organization=organization, when__lte=when).latest('when')
        except OrganizationRating.DoesNotExist:
            last = OrganizationRating()  # create an empty one

        # 2017 08 29 bugfix: you can have a rating of 0, eg when all urls are dead or perfect
        # yes, a calculation can go to 0 when all urls are dead.
        # so checking for total_calculation here doesn't make sense.
        # if the rating is different, then save it.

        #                     "rated on": "%s",\n\ -> removed due to it's always
        # changing the calculation. ... do we want the "when" field to be auto updated? Or should
        # the "when" field be read as a "since" field... and the rating didn't change since then?
        # It's the last bit: so "when" should be "since".
        organizationratingtemplate = """
    {
    "organization": {
        "name": "%s",
        "rating": "%s",
        "urls": [%s]
        }
    }"""

        organization_json = (organizationratingtemplate % (organization.name, total_rating,
                                                           total_calculation))
        # print(organization_json)
        parsed = json.loads(organization_json)
        organization_json_checked = json.dumps(parsed, indent=4)
        # print("%s %s" % (last.calculation, total_calculation))
        if last.calculation != organization_json_checked:
            logger.debug("The calculation (json) has changed, so we're saving this report, rating.")
            u = OrganizationRating()
            u.organization = organization
            u.rating = total_rating
            u.when = when
            u.calculation = organization_json_checked
            u.save()
        else:
            logger.debug("The calculation is still the same, not creating a new OrganizationRating")

    # also callable as admin action
    @staticmethod
    def rate_url(url, when=""):

        # If there is no time slicing, then it's today.
        if not when:
            when = datetime.now(pytz.utc)

        explanation, rating = DetermineRatings.get_url_score_modular(url, when)

        # avoid duplication. We think the explanation is the most unique identifier.
        # therefore the order in which URLs are grabbed (if there are new ones) is important.
        # it cannot be random, otherwise the explanation will be different every time.

        # it's very possible there is no rating yet
        # we do show the not_resolvable history.
        # todo: possibly cachable, saving thousands of queries.
        try:
            last_url_rating = \
                UrlRating.objects.filter(url=url,
                                         url__urlrating__when__lte=when,
                                         url__is_dead=False).latest("when")
        except ObjectDoesNotExist:
            # todo, fix broad exception.
            last_url_rating = UrlRating()  # todo: evaluate if this is a wise approach.

        # possibly a bug: you're not getting the latest rating... you get the whole set and
        # then get the first one (the oldest)... that's why some urls keep getting ratings.
        # last_url_rating = UrlRating.objects.filter(url=url, url__urlrating__when__lte=when)[:1]
        # if last_url_rating.exists():
        #    last_url_rating = last_url_rating.get()
        # else:
        #    last_url_rating = UrlRating()  # create an empty one

        if explanation and last_url_rating.calculation != explanation:
            u = UrlRating()
            u.url = url
            u.rating = rating
            u.when = when
            u.calculation = explanation
            u.save()

    """
from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Url, Organization
u = Url.objects.all().filter(url="loket.zaanstad.nl").get()
DetermineRatings.get_url_score_modular(u)
DetermineRatings.rate_url(u)
o = Organization.objects.all().filter(name="Zaanstad").get()
DetermineRatings.rate_organization(o)
    """

    @staticmethod
    def get_url_score_modular(url, when=""):
        if not when:
            when = datetime.now(pytz.utc)

        logger.debug("Calculating url score for %s on %s" % (url.url, when))

        endpoints = DetermineRatings.get_relevant_endpoints_at_timepoint(url, when)

        # general reporting json:
        url_rating_template = """
        {
        "url": {
            "url": "%s",
            "points": "%s",
            "endpoints": [%s]
            }
        }"""

        endpoint_template = """
            {
            "%s:%s": {
                "ip": "%s",
                "port": "%s",
                "ratings": [%s]
                }
            }"""

        rating = 0
        endpoint_jsons = []
        for endpoint in endpoints:
            (scanner_tls_qualys_rating, scanner_tls_qualys_json) = \
                DetermineRatings.get_report_from_scanner_tls_qualys(endpoint, when)

            (scanner_http_plain_rating, scanner_http_plain_json) = \
                DetermineRatings.get_report_from_scanner_http_plain(endpoint, when)

            jsons = []
            jsons.append(scanner_tls_qualys_json) if scanner_tls_qualys_json else ""
            jsons.append(scanner_http_plain_json) if scanner_http_plain_json else ""

            rating += int(scanner_tls_qualys_rating) + int(scanner_http_plain_rating)

            if jsons:
                endpoint_jsons.append((endpoint_template % (endpoint.ip,
                                                           endpoint.port,
                                                           endpoint.ip,
                                                           endpoint.port,
                                                           ",".join(jsons))))

        # now prepare the url bit:
        if endpoint_jsons:
            url_json = url_rating_template % (url.url, rating, ",".join(endpoint_jsons))
            # logger.debug(url_json)
            parsed = json.loads(url_json)
            url_json = json.dumps(parsed)  # nice format
            return url_json, rating
        else:
            # empty explanations don't get saved.
            return "", 0

    # todo: can be abstracted.
    @staticmethod
    def get_report_from_scanner_http_plain(endpoint, when):
        from failmap_admin.scanners.models import EndpointGenericScan

        if endpoint.protocol != "http":
            logger.debug("Endpoint is not on the right protocol. Nothing to find.")
            return 0, ""

        rating_template = """
                {
                "http_plain": {
                    "explanation": "%s",
                    "points": "%s",
                    "since": "%s",
                    "last_scan": "%s"
                    }
                }"""

        try:
            scan = EndpointGenericScan.objects.filter(endpoint=endpoint,
                                                      last_scan_moment__lte=when,
                                                      type="plain_https")
            scan = scan.latest('rating_determined_on')

            json = (rating_template % (scan.explanation,
                                       scan.rating,
                                       scan.rating_determined_on,
                                       scan.last_scan_moment))

            return scan.rating, json
        except ObjectDoesNotExist:
            logger.debug("No http plain scan on endpoint %s." % endpoint)
            return 0, ""



    @staticmethod
    def get_report_from_scanner_tls_qualys(endpoint, when):

        if endpoint.port != 443 and endpoint.protocol != "https":
            logger.debug("Endpoint is not on the right port and protocol. Nothing to find.")
            return 0, ""

        explanations = {
            "F": "F - Failing TLS",
            "D": "D",
            "C": "C",
            "B": "B",
            "A-": "A-, Good",
            "A": "A, Good",
            "A+": "A+, Perfect",
            "T": "Chain of trust missing",
            "0": "No TLS discovered, possibly another service available.",
        }

        # 0? that's port 443 without using TLS. That is extremely rare. In that case...
        # 0 is many cases a "not connect to server" error currently. But there is more.
        # todo: when certificate mismatch, give 200 points: should be cleaned up.
        ratings = {"T": 500, "F": 1000, "D": 400, "C": 200,
                   "B": 100, "A-": 0, "A": 0, "A+": 0, "0": 0}

        tlsratingtemplate = """
                {
                "tls_qualys": {
                    "explanation": "%s",
                    "points": "%s",
                    "since": "%s",
                    "last_scan": "%s"
                    }
                }"""

        try:
            scan = TlsQualysScan.objects.filter(endpoint=endpoint, scan_moment__lte=when)
            scan = scan.latest('rating_determined_on')

            # Ignore ratings with 0: then there was no TLS, and we don't know if there is
            # a normal website on port 80.
            if scan.qualys_rating != '0':
                starttls_json = (tlsratingtemplate %
                                 (explanations[scan.qualys_rating], ratings[scan.qualys_rating],
                                  scan.rating_determined_on, scan.scan_moment))

                rating = ratings[scan.qualys_rating]

                return rating, starttls_json
        except TlsQualysScan.DoesNotExist:
            # can happen that a rating simply isn't there yet. Perfectly possible.
            logger.debug("No tls qualys scan on endpoint %s." % endpoint)
            pass

        return 0, ""

    @staticmethod
    # removed port=443, and protocol="https", since we want all types of scans to show.
    def get_relevant_endpoints_at_timepoint(url, when):

        endpoints = Endpoint.objects.all()

        # all endpoints in the past given the timeframe, they can be dead.
        dead_endpoints = endpoints.filter(
            url=url,
            discovered_on__lte=when,
            is_dead=True,
            is_dead_since__gte=when,
        )
        logger.debug("Dead endpoints for this url:  %s" % dead_endpoints.count())

        # all endpoints that are still alive on the timeperiod
        existing_endpoints = endpoints.filter(
            url=url,
            discovered_on__lte=when,
            is_dead=False,
        )

        logger.debug("Alive endpoints for this url: %s" % existing_endpoints.count())

        endpoint_list = list(dead_endpoints) + list(existing_endpoints)

        return endpoint_list

    # todo: more modular approach
    # Know what scanners exist.
    # Ask each scanner the newest result for a certain date
    # add a weight to it
    # store it as a url rating
    # we do this per hour, only update the last rating if there is an update
    # and we do this for at most the last hour. (and we can go back in time to fill the db
    # and get those sweet rating improvements.
    # does not add information when there is nothing to find for this url.
    #
    # Extra: this does not check if all endpoints are dead (and thus the url)... it shouldn't
    # because the scanner should check that.
    @staticmethod
    def get_url_score(url, when):
        print("Calculating score for %s on %s" % (url.url, when))

        explanation = ""
        rating = 0

        # This is done in a few simple and readable steps.

        endpoints = Endpoint.objects.all()

        # all endpoints in the past given the timeframe
        dead_endpoints = endpoints.filter(
            url=url,
            discovered_on__lte=when,
            is_dead=True,
            is_dead_since__gte=when,
            port=443,
            protocol="https"
        )
        print("Dead endpoints for this url:  %s" % dead_endpoints.count())

        # all endpoints that are still alive on the timeperiod
        existing_endpoints = endpoints.filter(
            url=url,
            discovered_on__lte=when,
            is_dead=False,
            port=443,
            protocol="https"
        )

        print("Alive endpoints for this url: %s" % existing_endpoints.count())

        # higly inefficient merging of results :)
        endpoint_list = list(dead_endpoints) + list(existing_endpoints)

        explanations = {
            "F": "F - Failing TLS",
            "D": "D",
            "C": "C",
            "B": "B",
            "A-": "A-, Good",
            "A": "A, Good",
            "A+": "A+, Perfect",
            "T": "Chain of trust missing",
            "0": "No TLS discovered, possibly another service available.",
        }

        # 0? that's port 443 without using TLS. That is extremely rare. In that case...
        # 0 is many cases a "not connect to server" error currently.
        # todo: remove 0 ratings from the report. They are useless.
        # todo: check for existing endpoint for a date range.
        ratings = {"T": 500, "F": 1000, "D": 400, "C": 200,
                   "B": 100, "A-": 0, "A": 0, "A+": 0, "0": 0}

        urlratingtemplate = \
            '{\n\
                "url": {\n\
                    "url": "%s",\n\
                    "points": "%s",\n\
                    "endpoints": [%s]\n\
                    \n\
                }\n\
            }\n'

        endpointtemplate = \
            '{\n\
                "%s:%s": {\n\
                    "ip": "%s",\n\
                    "port": "%s",\n\
                    "ratings": [%s]\n\
                    \n\
                }\n\
            }\n'

        tlsratingtemplate = \
            '{\n\
                "TLS_Qualys\": {\n\
                    "explanation": "%s",\n\
                    "points": "%s",\n\
                    "since": "%s",\n\
                    "last_scan": "%s"\n\
                }\n' \
            '}\n'

        starttls_json = ""
        endpoint_json = ""

        # todo: refactor to request a number of points in a more generic way.
        # an endpoint at most has 1 TLS rating.
        for endpoint in endpoint_list:
            try:
                scan = TlsQualysScan.objects.filter(endpoint=endpoint, scan_moment__lte=when)
                scan = scan.latest('rating_determined_on')

                # Ignore ratings with 0: then there was no TLS, and we don't know if there is
                # a normal website on port 80.
                if scan.qualys_rating != '0':
                    starttls_json = (tlsratingtemplate %
                                     (explanations[scan.qualys_rating], ratings[scan.qualys_rating],
                                      scan.rating_determined_on, scan.scan_moment))

                    # you can only add the comma if there are multiple items...
                    if endpoint_json:
                        endpoint_json += ", "

                    endpoint_json += (endpointtemplate % (endpoint.ip, endpoint.port,
                                                          endpoint.ip, endpoint.port,
                                                          starttls_json))

                    rating += ratings[scan.qualys_rating]
            except TlsQualysScan.DoesNotExist:
                # can happen that a rating simply isn't there yet. Perfectly possible.
                print("No scan on endpoint %s." % endpoint)
                pass

        # if there is not a single endpoint that has data... then well... don't return
        # an explanation and make sure this is not saved.
        if endpoint_json:
            url_json = urlratingtemplate % (url.url, rating, endpoint_json)
            # print(url_json)
            parsed = json.loads(url_json)
            url_json = json.dumps(parsed, indent=4)  # nice format
            return url_json, rating
        else:
            # empty explanations don't get saved.
            return "", 0
