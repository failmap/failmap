import json
from datetime import datetime

import pytz
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta  # history
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint, TlsQualysScan

from .models import OrganizationRating, UrlRating

# todo: determine ratings over the past few months by changing the When.


class DetermineRatings:
    """
    Here the magic happens for determining a rating for a url and ultimately an organization.

    How we approach this: we first make daily ratings for the last days and store them
        except if it results in the same rating as previous.

    """

    def get_weekly_intervals(self):
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

    def rate_organizations(self, create_history=False):
        # todo: we should create some protection that there are not insane amounts of ratings
        # created.
        times = self.get_weekly_intervals() if create_history else [datetime.now(pytz.utc)]

        os = Organization.objects.all()
        for when in times:
            for o in os:
                self.rate_organization(o, when)

    def rate_urls(self, create_history=False):

        times = self.get_weekly_intervals() if create_history else [datetime.now(pytz.utc)]

        urls = Url.objects.filter(is_dead=False)

        for when in times:
            for url in urls:
                self.rate_url(url, when)

    # also callable as admin action
    # this is 100% based on url ratings, just an aggregate of the last status.
    # make sure the URL ratings are up to date, they will check endpoints and such.
    def rate_organization(self, organization, when=""):
        print("rating on %s organization %s" % (when, organization))
        """
        Perhaps i don't understand SQL very well... but this is the case
        that is currently going wrong.

        The query that i wanted, which accounts for multiple ratings a the same time:

        SELECT "url"."url", COUNT("url"."url") AS "n_urls", "map_urlrating"."id"
        FROM "url"
        INNER JOIN "map_urlrating" ON ("url"."id" = "map_urlrating"."url_id")
        WHERE "url"."organization_id" = 289 AND "url"."is_dead" = False
        GROUP BY "url"."url"
        HAVING ("map_urlrating"."when" = (MAX("map_urlrating"."when"))
        AND "map_urlrating"."id" = (MAX("map_urlrating"."id")))

        This was simply not possible via the ORM since there where multiple
        things thrown in the group by that i didn't ask for.

        Using this i came pretty close:
        ratings = ratings.filter(urlrating__when=Max("urlrating__when"),
                                 urlrating__id=Max("urlrating__id"))

        But it throws in a few extra group by's on urlrating and id. Which make the
        resultset even larger. I can't think in sets using the django orm (yet). :(

        Using the MAX() annotation you get the Max ID, but what if that is NOT the latest
        over time.

        Both go wrong, in adding an additional group by:
        ratings = Url.objects
        ratings = ratings.values("url")
        ratings = ratings.filter(organization=organization, is_dead=False)
        ratings = ratings.filter(urlrating__when=Max("urlrating__when"))
        ratings = ratings.annotate(n_urls=Count("url"))
        # ratings = ratings.annotate(max_id=Max("urlrating__id"))

        ratings = UrlRating.objects
        ratings = ratings.values("id")
        ratings = ratings.filter(url__organization=organization, url__is_dead=False)
        ratings = ratings.filter(when=Max("when"))
        ratings = ratings.annotate(n_urls=Count("url"))

        GROUP BY "map_urlrating"."id", "map_urlrating"."when" H

        and all we want is exactly that query WITHOUT the group by on "when".

        That's why you don't want to annotate (left outer join) but filter (inner join).
        Only the ORM decides i need to also group by, which is just not ok.

        The filter often creates an extra table, which is even more annoying.

        :param organization:
        :param when: slide through time
        :return:
        """
        # sum the latest url ratings where URL is not dead of this organization.
        # save that sum as the most recent rating. That will be retrieved by the site.
        # in a query that we can possibly rewrite.

        # there will always be 1 latest rating per Url, so we can have some insane query here
        #   ratings = Url.objects
        #   ratings = ratings.values("url")
        #   ratings = ratings.filter(organization=organization, is_dead=False)
        #   ratings = ratings.filter(urlrating__when=Max("urlrating__when"))
        #   ratings = ratings.annotate(n_urls=Count("url"))
        # ratings = ratings.annotate(max_id=Max("urlrating__id"))

        #    ratings = UrlRating.objects
        #    ratings = ratings.values("id", "when")
        #    ratings = ratings.filter(url__organization=organization, url__is_dead=False)
        #    ratings = ratings.filter(when=Max("when"))
        #    ratings = ratings.annotate(n_urls=Count("url"))

        # since all added a _> BY "map_urlrating"."id", "map_urlrating"."when" H
        # just overwrite the query with what we really want. The ORM and no search results
        # helped, taking too much time, costing half a day for something trivial.
        # i can't imagine that this isn't a standard usecase...
        #   r  tings = ratings.raw('SELECT "map_urlrating"."id", "map_urlrating"."when", '
        #                         '"map_urlrating"."rating", "map_urlrating"."calculation",'
        #                         'COUNT("map_urlrating"."url_id") AS "n_urls" '
        #                         'FROM "map_urlrating" '
        #                         'INNER JOIN "url" ON ("map_urlrating"."url_id" = "url"."id") '
        #                         'WHERE ("url"."organization_id" = 289 '
        #                         'AND "url"."isDead" = 0) '
        #                         'GROUP BY "map_urlrating"."id"'
        #                         'HAVING "map_urlrating"."when" = (MAX("map_urlrating"."when"))')

        # If there is no time slicing, then it's today.
        if not when:
            when = datetime.now(pytz.utc)

        total_rating = 0
        total_calculation = ""

        # ok, fuck it... let's do this in two steps then: first find the urls
        # then find the max rating in a separate query, cause we're fucking idiots

        # todo: servername maakt endpoint uniek, dat is fout. maak migratie. Bewaar de nieuwste.

        # double urls:
        # select domain, ip, count(id), min(id) from scanners_endpoint group by domain, ip having
        # count(domain)>1 and count(ip)>1 order by id desc

        # delete qualys scans: DELETE FROM scanner_tls_qualys WHERE endpoint_id IN (select min(id)
        # from scanners_endpoint group by domain, ip
        # having count(domain)>1 and count(ip)>1 order by id desc)
        # delete endpoints:
        # DELETE FROM scanners_endpoint WHERE id IN (select min(id) from scanners_endpoint
        # group by domain, ip having count(domain)>1 and count(ip)>1 order by id desc)
        # moet je 10x uitvoeren ofzo. gaat iets niet helemaal lekker mee..

        # todo: de servername kan je soms wel andere urls uit halen, maar nihil.
        # daarbij kan dat iets zijn waar gewoon op gecheckt wordt per keer scan, als nieuw url,
        # dan toevoegen.

        # todo: de laatste check moet ook in het raport komen te staan, niet alleen sinds wanneer
        # een probleem is geconstateerd. Dat hebben we gebouwd om ruimte te besparen. Anders wordt
        # er bij iedere rating nieuwe data opgeslagen: dat willen we voorkomen.
        # we bufferen de ratings om tijdrovende berekeningen te besparen.

        # there might be a buggy state where the endpoints are dead, but the url itself is
        # not declared dead. The scanner should have killed the endpoints too...
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
        organizationratingtemplate = \
            '{\n\
                "organization": {\n\
                    "name": "%s",\n\
                    "rating": "%s",\n\
                    "urls": [%s]\n\
                    \n\
                }\n\
            }\n'

        organization_json = (organizationratingtemplate % (organization.name, total_rating,
                                                           total_calculation))
        # print(organization_json)
        parsed = json.loads(organization_json)
        organization_json_checked = json.dumps(parsed, indent=4)

        # print("%s %s" % (last.calculation, total_calculation))
        if last.calculation != organization_json_checked:
            u = OrganizationRating()
            u.organization = organization
            u.rating = total_rating
            u.when = when
            u.calculation = organization_json_checked
            u.save()

    # also callable as admin action
    def rate_url(self, url, when=""):

        # If there is no time slicing, then it's today.
        if not when:
            when = datetime.now(pytz.utc)

        explanation, rating = self.get_url_score(url, when)

        # avoid duplication. We think the explanation is the most unique identifier.
        # therefore the order in which URLs are grabbed (if there are new ones) is important.
        # it cannot be random, otherwise the explanation will be different every time.

        # it's very possible there is no rating yet
        try:
            last_url_rating = \
                UrlRating.objects.filter(url=url, url__urlrating__when__lte=when).latest("when")
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
    def get_url_score(self, url, when):
        print("calculating score on %s for %s" % (when, url.url))

        explanation = ""
        rating = 0

        # to prevent django orm group by fuckery, this is done in a few simple and readable steps.

        # 1: get latest alive endpoints+scans of this URL for qualys after When
        endpoints = Endpoint.objects.all()
        # qualys endpoints are HTTPS on port 443
        endpoints = endpoints.filter(
            url=url,
            is_dead=False,
            port=443,
            protocol="https"
        )

        # todo: add database indexes. can we inspect with sqlite?
        explanations = {
            "F": "F - Failing TLS",
            "D": "D",
            "C": "C",
            "B": "B",
            "A-": "A-, Good",
            "A": "A, Good",
            "A+": "A+, Perfect",
            "T": "Chain of trust missing",
            "0": "No TLS used initially: no integrity and no confidentiality",
        }

        ratings = {"T": 500, "F": 1000, "D": 400, "C": 200,
                   "B": 100, "A-": 0, "A": 0, "A+": 0, "0": 200}

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
                    "since": "%s"\n\
                }\n' \
            '}\n'

        starttls_json = ""
        endpoint_json = ""

        for endpoint in endpoints:
            try:
                scan = TlsQualysScan.objects.filter(endpoint=endpoint,
                                                    scan_moment__lte=when)
                scan = scan.latest('rating_determined_on')

                # currently there is only one rating for an endpoint... we need to refactor this.
                # todo: refactor the way this list is created and populated. Extra table?
                # you can only have one TLS rating on an endpoint.
                starttls_json = (tlsratingtemplate %
                                 (explanations[scan.qualys_rating], ratings[scan.qualys_rating],
                                  scan.rating_determined_on))  # was "scan_moment" but that is
                # ... updated frequently: every scan. But the rating determined on is not.

                # you can only add the comma if there are multiple items...
                if endpoint_json:
                    endpoint_json += ", "

                endpoint_json += (endpointtemplate % (endpoint.ip, endpoint.port,
                                                      endpoint.ip, endpoint.port, starttls_json))

                rating += ratings[scan.qualys_rating]
            except TlsQualysScan.DoesNotExist:
                # can happen that a rating simply isn't there yet. Perfectly possible.
                pass

        #
        url_json = urlratingtemplate % (url.url, rating, endpoint_json)
        # print(url_json)
        # load it up in a json parser to give it a nice format. (why not make a json object then?)
        parsed = json.loads(url_json)
        url_json = json.dumps(parsed, indent=4)

        return url_json, rating
