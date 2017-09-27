import json
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
        times = DetermineRatings.get_weekly_intervals() if create_history else [
            datetime.now(pytz.utc)]

        os = Organization.objects.all()
        for when in times:
            for o in os:
                DetermineRatings.rate_organization(o, when)

    @staticmethod
    def rate_urls(create_history=False):

        times = DetermineRatings.get_weekly_intervals() if create_history else [
            datetime.now(pytz.utc)]

        urls = Url.objects.filter(is_dead=False)

        for when in times:
            for url in urls:
                DetermineRatings.rate_url(url, when)

    @staticmethod
    def rate_organizations_efficient(create_history=False):
        os = Organization.objects.all().order_by('name')
        if create_history:
            for o in os:
                times = DetermineRatings.significant_times(organization=o)
                for time in times:
                    DetermineRatings.rate_organization(o, time)
        else:
            for o in os:
                DetermineRatings.rate_organization(o, datetime.now(pytz.utc))

    @staticmethod
    def rate_organization_efficient(organization, create_history=False):
        if create_history:
            times = DetermineRatings.significant_times(organization=organization)
            for time in times:
                DetermineRatings.rate_organization(organization, time)
        else:
            DetermineRatings.rate_organization(organization, datetime.now(pytz.utc))

    @staticmethod
    def rate_organization_urls_efficient(organization, create_history=False):

        urls = Url.objects.filter(is_dead=False, organization=organization).order_by('url')

        if create_history:
            for url in urls:
                times = DetermineRatings.significant_times(url=url)
                for time in times:
                    DetermineRatings.rate_url(url, time)
        else:
            for url in urls:
                DetermineRatings.rate_url(url, datetime.now(pytz.utc))

    @staticmethod
    def rate_urls_efficient(create_history=False):

        urls = Url.objects.filter(is_dead=False).order_by('url')

        if create_history:
            for url in urls:
                times = DetermineRatings.significant_times(url=url)
                for time in times:
                    DetermineRatings.rate_url(url, time)
        else:
            for url in urls:
                DetermineRatings.rate_url(url, datetime.now(pytz.utc))

    @staticmethod
    def clear_organization_and_urls(organization):
        UrlRating.objects.all().filter(url__organization=organization).delete()
        OrganizationRating.objects.all().filter(organization=organization).delete()

    @staticmethod
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

        # todo: reduce this to one moment per day only, otherwise there will be a report for
        # todo: the order of this list should be chronological: otherwise ratings get overwritten?
        # ^ it should be different every time. So, this doesn't matter.
        # for every scan: that is highly inefficient.
        logger.debug("Found amount of dates, optimizing: %s", len(datetimes))

        # take the last moment of the date, so the scan will have happened at the correct time
        datetimes2 = [x.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc) for x in
                      datetimes]
        datetimes2 = list(set(datetimes2))
        datetimes2.sort()

        # if the last datetime2 is today, then just reduce it to NOW to cause less confusion in
        # the dataset (don't place ratings in the future).
        if datetimes2:
            if datetimes2[len(datetimes2)-1] == datetime.now().replace(
                    hour=23, minute=59, second=59, microsecond=999999, tzinfo=pytz.utc):
                datetimes2[len(datetimes2)-1] = datetime.now(pytz.utc)

            logger.debug("Found amount of dates: %s", len(datetimes2))
            # logger.debug("Relevant dates for organization/url: %s", datetimes2)

        return datetimes2

    # also callable as admin action
    # this is 100% based on url ratings, just an aggregate of the last status.
    # make sure the URL ratings are up to date, they will check endpoints and such.

    @staticmethod
    def rate_organizations(organizations, when=""):
        # since a url can now have multiple organizations, you should rate each one separately
        for organization in organizations.all():
            DetermineRatings.rate_organization(organization, when)

    @staticmethod
    def rate_organization(organization, when=""):

        # If there is no time slicing, then it's today.
        if not when:
            when = datetime.now(pytz.utc)

        logger.debug("rating on: %s, Organization %s" % (when, organization))

        total_rating = 0
        total_calculation = ""

        # hij gaat alle urls ophalen, ookal zijn die lang niet meer levend op een bepaalde periode
        # je moet de relevante urls voor deze periode bepalen, sommige zijn dood, anderen niet
        # net als dat je endpoints bij urls bepaalt(!)
        # urls = Url.objects.filter(organization=organization, is_dead=False)
        urls = DetermineRatings.get_relevant_urls_at_timepoint(organization=organization,
                                                               when=when)

        for url in urls:
            try:
                urlratings = UrlRating.objects.filter(url=url, when__lte=when)
                urlratings = urlratings.values("rating", "calculation")
                urlrating = urlratings.latest("when")  # kills the queryset, results 1

                # some urls are never rated
                total_rating += urlrating["rating"]

                # when there are multiple urls, add the mandatory comma....
                if total_calculation:
                    total_calculation += ","

                total_calculation += urlrating["calculation"]
            except UrlRating.DoesNotExist:
                logger.warning("Url has no rating at this moment: %s %s" % (url, when))
                pass

        try:
            last = OrganizationRating.objects.filter(
                organization=organization, when__lte=when).latest('when')
        except OrganizationRating.DoesNotExist:
            logger.debug("Could not find the last organization rating, creating a dummy one.")
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
    }""".strip()

        organization_json = (organizationratingtemplate % (organization.name, total_rating,
                                                           total_calculation))
        # print(organization_json)
        # verify the JSON is correct
        parsed = json.loads(organization_json)
        organization_json_checked = json.dumps(parsed)
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
    @staticmethod
    def rate_url(url, when=""):

        if not when:
            when = datetime.now(pytz.utc)

        explanation, rating = DetermineRatings.get_url_score_modular(url, when)

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

        """
        A relevant endpoint is an endpoint that is still alive or was alive at the time.
        Due to being alive (or at the time) it can get scores from various scanners more easily.

        Afterwards we'll check if at this time there also where dead endpoints.
        Dead endpoints add 0 points to the rating, but it can lower a rating.(?)
        """
        endpoints = DetermineRatings.get_relevant_endpoints_at_timepoint(url, when)

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
                                                            endpoint.protocol,
                                                            ",".join(jsons))))

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
        #         DetermineRatings.get_report_from_scanner_dead(endpoint, when)
        #     jsons.append(scanner_dead_json) if scanner_dead_json else ""
        #     int(scanner_dead_rating)

        # now prepare the url bit:
        if endpoint_jsons:
            url_json = url_rating_template % (url.url, rating, ",".join(endpoint_jsons))
            # logger.debug(url_json)
            # verify correctness of json:
            parsed = json.loads(url_json)
            url_json = json.dumps(parsed)  # nice format
            return url_json, rating
        else:
            # empty explanations don't get saved.
            return "", 0

    @staticmethod
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

    # todo: can be abstracted.
    @staticmethod
    def get_report_from_scanner_http_plain(endpoint, when):
        logger.debug("get_report_from_scanner_http_plain")

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
                }""".strip()

        try:
            scan = EndpointGenericScan.objects.filter(endpoint=endpoint,
                                                      last_scan_moment__lte=when,
                                                      type="plain_https",
                                                      )
            scan = scan.latest('rating_determined_on')

            json = (rating_template % (scan.explanation,
                                       scan.rating,
                                       scan.rating_determined_on,
                                       scan.last_scan_moment))

            logger.debug("plain_https: On %s, Endpoint %s, Rated %s" %
                         (when, endpoint, scan.rating))
            return scan.rating, json
        except ObjectDoesNotExist:
            logger.debug("No http plain scan on endpoint %s." % endpoint)
            return 0, ""

    @staticmethod
    def get_report_from_scanner_tls_qualys(endpoint, when):
        logger.debug("get_report_from_scanner_tls_qualys")

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
            "I": "Certificate not valid for domain name",  # Custom message
            "0": "-",
        }

        # 0? that's port 443 without using TLS. That is extremely rare. In that case...
        # 0 is many cases a "not connect to server" error currently. But there is more.
        # Now checking messages returned from qualys. Certificate invalid for domain name now
        # is awarded points.
        ratings = {"T": 500,
                   "F": 1000,
                   "D": 400,
                   "I": 200,
                   "C": 200,
                   "B": 100,
                   "A-": 0,
                   "A": 0,
                   "A+": 0,
                   "0": 0}

        tlsratingtemplate = """
                {
                "tls_qualys": {
                    "explanation": "%s",
                    "points": "%s",
                    "since": "%s",
                    "last_scan": "%s"
                    }
                }""".strip()

        try:
            scan = TlsQualysScan.objects.filter(endpoint=endpoint, scan_moment__lte=when)
            scan = scan.latest('rating_determined_on')

            # configuration errors
            if scan.qualys_message == "Certificate not valid for domain name":
                scan.qualys_rating = "I"

            if scan.qualys_rating != '0':
                starttls_json = (tlsratingtemplate %
                                 (explanations[scan.qualys_rating], ratings[scan.qualys_rating],
                                  scan.rating_determined_on, scan.scan_moment))

                rating = ratings[scan.qualys_rating]

                logger.debug(
                    "TLS: On %s, Endpoint %s, Rated %s" % (when, endpoint, scan.qualys_rating))
                return rating, starttls_json
            else:
                logger.debug("TLS: This tls scan resulted in no https. Not returning a score.")
                return 0, ""
        except TlsQualysScan.DoesNotExist:
            # can happen that a rating simply isn't there yet. Perfectly possible.
            logger.debug("No tls qualys scan on endpoint %s." % endpoint)
            pass

        return 0, ""

    @staticmethod
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
            has_endpoints = DetermineRatings.get_relevant_endpoints_at_timepoint(url=url, when=when)
            if has_endpoints:
                logger.debug(
                    "The url %s is relevant on %s and has endpoints: " % (url, when))
                url_list_with_relevant_endpoints.append(url)
            else:
                logger.debug("While the url %s was relevant on %s, "
                             "it does not have any relevant endpoints" % (url, when))

        return url_list_with_relevant_endpoints

    @staticmethod
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
            """.strip() % organization.name
            r.save()

    @staticmethod
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
