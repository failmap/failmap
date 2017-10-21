import collections
import json
from datetime import datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page
from pkg_resources import get_distribution

from failmap_admin.map.models import OrganizationRating, UrlRating
from failmap_admin.organizations.models import Organization, Url

one_minute = 60
one_hour = 60 * 60
one_day = 24 * 60 * 60
ten_minutes = 60 * 10

@cache_page(one_hour)
def index(request):
    # todo: move to vue translations on client side. There are many javascript components that
    # also need to be translated some way.
    """
        The map is simply a few files that are merged by javascript on the client side.
        Django templating is avoided as much as possible.
    :param request:
    :return:
    """

    return render(request, 'map/index.html', {
        'version': get_distribution(__name__.split('.', 1)[0]).version,
    })

@cache_page(one_day)
def robots_txt(request):
    return render(request, 'map/robots.txt', content_type="text/plain")

@cache_page(one_day)
def security_txt(request):
    return render(request, 'map/security.txt', content_type="text/plain")

@cache_page(ten_minutes)
def organization_report(request, organization_id, weeks_back=0):
    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    # getting the latest report.
    try:
        r = Organization.objects.filter(pk=organization_id, organizationrating__when__lte=when). \
            values('organizationrating__rating',
                   'organizationrating__calculation',
                   'organizationrating__when',
                   'name',
                   'pk').latest('organizationrating__when')
        # latest replaced: order_by('-organizationrating__when')[:1].get()

        report_json = """
{
    "rating": %s,
    "when": "%s",
    "name": "%s",
    "id": %s,
    "calculation": %s
}
        """
        report_json = report_json % (r['organizationrating__rating'],
                                     r['organizationrating__when'],
                                     r['name'],
                                     r['pk'],
                                     r['organizationrating__calculation'])
        # print(report_json)
    except Organization.DoesNotExist:
        report_json = "{}"

    x = json.loads(report_json)

    return JsonResponse(x, json_dumps_params={'indent': 2}, safe=False)


def string_to_delta(string_delta):
    value, unit, _ = string_delta.split()
    return timedelta(**{unit: float(value)})

# slow in sqlite, seemingly fast in mysql


@cache_page(one_day)
def terrible_urls(request, weeks_back=0):
    # this would only work if the latest endpoint is actually correct.
    # currently this goes wrong when the endpoints are dead but the url still resolves.
    # then there should be an url rating of 0 (as no endpoints). But we don't save that yet.
    # So this feature cannot work until the url ratings are actually correct.
    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    data = {
        "metadata": {
            "type": "urllist",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": "-",
        },
        "urls":
            [

        ]
    }

    cursor = connection.cursor()

    # 0.5 seconds
    # sql_old = '''
    #     SELECT
    #         rating,
    #         organization.name,
    #         organizations_organizationtype.name,
    #         organization.id,
    #         `when`,
    #         organization.twitter_handle,
    #         url.url,
    #         url.isdead,
    #         url.not_resolvable
    #     FROM map_urlrating
    #     INNER JOIN
    #       url on url.id = map_urlrating.url_id
    #     LEFT OUTER JOIN
    #       url_organization on url_organization.url_id = url.id
    #     LEFT OUTER JOIN
    #       organization on organization.id = url_organization.organization_id
    #     INNER JOIN
    #       organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #     WHERE `when` <= '%s'
    #     AND `when` = (select MAX(`when`) FROM map_urlrating or2
    #           WHERE or2.url_id = map_urlrating.url_id AND `when` <= '%s')
    #     GROUP BY url.url
    #     HAVING(`rating`) > 999
    #     ORDER BY `rating` DESC, `organization`.`name` ASC
    #     ''' % (when, when)

    # 0.3 seconds, to 0.00
    sql = '''
            SELECT
                rating,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle,
                url.url,
                url.is_dead,
                url.not_resolvable
            FROM map_urlrating
            INNER JOIN
              url on url.id = map_urlrating.url_id
            LEFT OUTER JOIN
              url_organization on url_organization.url_id = url.id
            LEFT OUTER JOIN
              organization on organization.id = url_organization.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              (SELECT MAX(id) as id2 FROM map_urlrating or2
              WHERE `when` <= '%s' GROUP BY url_id) as x
              ON x.id2 = map_urlrating.id
            GROUP BY url.url
            HAVING(`rating`) > 999
            ORDER BY `rating` DESC, `organization`.`name` ASC
            LIMIT 20
            ''' % (when, )
    # print(sql)
    cursor.execute(sql)

    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "Rank": rank,
            "Url": i[6],
            "OrganizationID": i[3],
            "OrganizationType": i[2],
            "OrganizationName": i[1],
            "OrganizationTwitter": i[5],
            "Points": i[0],
            "DataFrom": i[4]
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["urls"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 4})


@cache_page(one_hour)
def topfail(request, weeks_back=0):
    
    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    data = {
        "metadata": {
            "type": "toplist",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": "Just fix it!",
        },
        "ranking":
            [

        ]
    }

    cursor = connection.cursor()

    """        INNER JOIN
          (SELECT MAX(id) as id2 FROM map_organizationrating or2
          WHERE `when` <= '%s' GROUP BY organization_id) as x
          ON x.id2 = map_organizationrating.id
    """

    # 0.5 seconds
    # sql = '''
    #         SELECT
    #             rating,
    #             organization.name,
    #             organizations_organizationtype.name,
    #             organization.id,
    #             `when`,
    #             organization.twitter_handle
    #         FROM map_organizationrating
    #         INNER JOIN
    #           organization on organization.id = map_organizationrating.organization_id
    #         INNER JOIN
    #           organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #         INNER JOIN
    #           coordinate ON coordinate.organization_id = organization.id
    #         WHERE `when` <= '%s' AND rating > 0
    #         AND `when` = (select MAX(`when`) FROM map_organizationrating or2
    #               WHERE or2.organization_id = map_organizationrating.organization_id AND `when` <= '%s')
    #         GROUP BY organization.name
    #         ORDER BY `rating` DESC, `organization`.`name` ASC
    #         LIMIT 30
    #         ''' % (when, when)

    # 0.00 seconds :)
    sql = '''
            SELECT
                rating,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle
            FROM map_organizationrating
            INNER JOIN
              organization on organization.id = map_organizationrating.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
            INNER JOIN
              (SELECT MAX(id) as id2 FROM map_organizationrating or2
              WHERE `when` <= '%s' GROUP BY organization_id) as x
              ON x.id2 = map_organizationrating.id
            GROUP BY organization.name
            HAVING rating > 0
            ORDER BY `rating` DESC, `organization`.`name` ASC
            LIMIT 10
            ''' % (when,)
    cursor.execute(sql)
    # print(sql)
    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "Rank": rank,
            "OrganizationID": i[3],
            "OrganizationType": i[2],
            "OrganizationName": i[1],
            "OrganizationTwitter": i[5],
            "Points": i[0],
            "DataFrom": i[4]
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 4})


# @cache_page(cache_time)
def topwin(request, weeks_back=0):
    # todo: still no django solution for the time dimension discovered, doing a manual query... :(
    # todo: add the twitter handle to the database etc...
    # at least it's fast.

    # This gets the organizations until a certain score that is seen as bad.
    # From that everything with > 0 points.

    # Would we reverse this, you'd get the top best. But honestly, only those with 0 points are good
    # enough.

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    data = {
        "metadata": {
            "type": "toplist",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": "You're now working with competence!",
        },
        "ranking":
            [

        ]
    }

    cursor = connection.cursor()

    # 0.50 sec
    # sql = '''
    #     SELECT
    #         rating,
    #         organization.name,
    #         organizations_organizationtype.name,
    #         organization.id,
    #         `when`,
    #         organization.twitter_handle
    #     FROM map_organizationrating
    #     INNER JOIN
    #       organization on organization.id = map_organizationrating.organization_id
    #     INNER JOIN
    #       organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #     INNER JOIN
    #       coordinate ON coordinate.organization_id = organization.id
    #     WHERE `when` <= '%s' AND rating = 0
    #     AND `when` = (select MAX(`when`) FROM map_organizationrating or2
    #           WHERE or2.organization_id = map_organizationrating.organization_id AND `when` <= '%s')
    #     GROUP BY organization.name
    #     ORDER BY LENGTH(`calculation`) DESC, `organization`.`name` ASC
    #     LIMIT 30
    #     ''' % (when, when)

    sql = '''
            SELECT
                rating,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle
            FROM map_organizationrating
            INNER JOIN
              organization on organization.id = map_organizationrating.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
          INNER JOIN
              (SELECT MAX(id) as id2 FROM map_organizationrating or2
              WHERE `when` <= '%s' GROUP BY organization_id) as x
              ON x.id2 = map_organizationrating.id
            GROUP BY organization.name
            HAVING rating = 0
            ORDER BY LENGTH(`calculation`) DESC, `organization`.`name` ASC
            LIMIT 10
            ''' % (when,)
    cursor.execute(sql)

    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "Rank": rank,
            "OrganizationID": i[3],
            "OrganizationType": i[2],
            "OrganizationName": i[1],
            "OrganizationTwitter": i[5],
            "Points": i[0],
            "DataFrom": i[4]
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 4})


def stats_determine_when(stat, weeks_back=0):
    if stat == 'now' or stat == 'earliest':
        when = datetime.now(pytz.utc)
    else:
        value, unit, _ = stat.split()
        when = datetime.now(pytz.utc) - relativedelta(**{unit: int(value)})

    # take into account the starting point
    # eg: now = 1 march, starting point: 1 january. Difference is N days. Subtract N from when.
    if weeks_back:
        when = when - relativedelta(weeks=int(weeks_back))

    return when


def recursively_default_dict():
    return collections.defaultdict(recursively_default_dict)


@cache_page(one_hour)
def stats(request, weeks_back=0):
    timeframes = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '3 weeks ago': 0, '1 month ago': 0,
             '2 months ago': 0, '3 months ago': 0}

    for stat in timeframes:

        when = stats_determine_when(stat, weeks_back)

        measurement = {'red': 0, 'orange': 0, 'green': 0,
                       'total_organizations': 0, 'total_score': 0, 'no_rating': 0,
                       'total_urls': 0, 'red_urls': 0, 'orange_urls': 0, 'green_urls': 0,
                       'included_organizations': 0, 'endpoints': 0,
                       "endpoint": collections.OrderedDict(), "explained": {}}

        ratings = OrganizationRating.objects.raw("""SELECT * FROM
                                           map_organizationrating
                                       INNER JOIN
                                       (SELECT MAX(id) as id2 FROM map_organizationrating or2
                                       WHERE `when` <= '%s' GROUP BY organization_id) as x
                                       ON x.id2 = map_organizationrating.id""" % when)

        noduplicates = []
        for rating in ratings:
            measurement["total_organizations"] += 1
            measurement["total_score"] += rating.rating

            if rating.rating < 200:
                measurement["green"] += 1

            if 199 < rating.rating < 1000:
                measurement["orange"] += 1

            if rating.rating > 999:
                measurement["red"] += 1

            # count the urls, from the latest rating. Which is very dirty :)
            # it will double the urls that are shared between organizations.
            # that is not really bad, it distorts a little.
            # we're forced to load each item separately anyway, so why not read it?
            x = json.loads(rating.calculation)
            measurement["total_urls"] += len(x['organization']['urls'])

            measurement["green_urls"] += sum(
                [int(l['points']) < 200 for l in x['organization']['urls']])
            measurement["orange_urls"] += sum(
                [199 < int(l['points']) < 1000 for l in x['organization']['urls']])
            measurement["red_urls"] += sum(
                [int(l['points']) > 999 for l in x['organization']['urls']])

            measurement["included_organizations"] += 1

            # make some generic stats for endpoints
            for url in x['organization']['urls']:
                if url['url'] in noduplicates:
                    continue
                noduplicates.append(url['url'])

                # endpoints

                # only add this to the first output, otherwise you have to make this a graph.
                # it's simply too much numbers to make sense anymore.
                # yet there is not enough data to really make a graph.
                # do not have duplicate urls in the stats.
                # ratings
                for endpoint in url['endpoints']:

                    # Only add the endpoint once for a series of ratings. And only if the
                    # ratings is not a repeated finding.
                    added_endpoint = False

                    for r in endpoint['ratings']:
                        # stats over all different ratings
                        if r['type'] not in measurement["explained"].keys():
                            measurement["explained"][r['type']] = {}
                            measurement["explained"][r['type']]['total'] = 0
                        if not r['explanation'].startswith("Repeated finding."):
                            if r['explanation'] not in measurement["explained"][r['type']].keys():
                                measurement["explained"][r['type']][r['explanation']] = 0

                            measurement["explained"][r['type']][r['explanation']] += 1
                            measurement["explained"][r['type']]['total'] += 1

                            # stats over all endpoints
                            # duplicates skew these stats.
                            # it is possible to have multiple endpoints of the same type
                            # while you can have multiple ipv4 and ipv6, you can only reach one
                            # therefore reduce this to have only one v4 and v6
                            if not added_endpoint:
                                added_endpoint = True
                                endpointtype = "%s/%s (%s)" % (endpoint["protocol"], endpoint["port"],
                                                       ("IPv4" if endpoint["v4"] == "True" else "IPv6"))
                                if endpointtype not in measurement["endpoint"].keys():
                                    measurement["endpoint"][endpointtype] = 0
                                measurement["endpoint"][endpointtype] += 1
                                measurement["endpoints"] += 1

        """                 measurement["total_organizations"] += 1
                            measurement["total_score"] += 0
                            measurement["no_rating"] += 1
        """
        measurement["endpoint"] = sorted(measurement["endpoint"].items())

        if measurement["included_organizations"]:
            measurement["red percentage"] = round((measurement["red"] /
                                                   measurement["included_organizations"]) * 100)
            measurement["orange percentage"] = round((measurement["orange"] /
                                                      measurement["included_organizations"]) * 100)
            measurement["green percentage"] = round((measurement["green"] /
                                                     measurement["included_organizations"]) * 100)
        else:
            measurement["red percentage"] = 0
            measurement["orange percentage"] = 0
            measurement["green percentage"] = 0

        if measurement["total_urls"]:
            measurement["red url percentage"] = round((measurement["red_urls"] /
                                                       measurement["total_urls"]) * 100)
            measurement["orange url percentage"] = round((measurement["orange_urls"] /
                                                          measurement["total_urls"]) * 100)
            measurement["green url percentage"] = round((measurement["green_urls"] /
                                                         measurement["total_urls"]) * 100)
        else:
            measurement["red url percentage"] = 0
            measurement["orange url percentage"] = 0
            measurement["green url percentage"] = 0

        stats[stat] = measurement

    return JsonResponse({"data": stats}, json_dumps_params={'indent': 4})


# this function doesn't give the relevant urls at the moment, it needs to select stuff better.
def urlstats(request, weeks_back=0):

    stats = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '3 weeks ago': 0, '1 month ago': 0,
             '2 months ago': 0, '3 months ago': 0}
    # reduce the numbers a bit, just scroll through time using the slider if you want to look back.
    # ,  '4 months ago': 0, '5 months ago': 0, '6 months ago': 0,
    #   '12 months ago': 0

    # todo: remove some empty url ratings / don't store that nonsense as it skews the stats
    # No: those have been added to close off url ratings...???
    # the stats should only contiain some meaningful data.
    # { "url": { "url": "legacy.gemeentewestland.nl", "points": "0", "endpoints": [] } }

    for stat in stats:
        # confusing decomposition to comply with mccabe
        when = stats_determine_when(stat, weeks_back)

        # Next to measurements in hard numbers, we also derive a conclusion in three categories:
        # red, orange and green. This is done to simplify the data, so it can be better understood.
        measurement = {'red': 0, 'orange': 0, 'green': 0,
                       'total_organizations': 0, 'total_score': 0, 'no_rating': 0,
                       'total_urls': 0, 'red_urls': 0, 'orange_urls': 0, 'green_urls': 0,
                       'included_organizations': 0}

        """
        What makes the difference from organizationratings? Why are there more urls?
        Does this have to do with dead endpoints? Or dead urls? Probably.

        now	            5144	243 (5%)	4422 (86%)	479 (9%)
        7 days ago	    5149	241 (5%)	4420 (86%)	488 (9%)
        2 weeks ago	    5143	3729 (73%)	1331 (26%)	83 (2%)
        3 weeks ago	    5042	3729 (74%)	1235 (24%)	78 (2%)
        1 month ago	    2342	1804 (77%)	496 (21%)	42 (2%)
        2 months ago	2357	1818 (77%)	496 (21%)	43 (2%)
        3 months ago	2357	1818 (77%)	496 (21%)	43 (2%)
        """

        ratings = UrlRating.objects.raw("""SELECT * FROM
                                           map_urlrating
                                       INNER JOIN
                                       (SELECT MAX(id) as id2 FROM map_urlrating or2
                                       WHERE `when` <= '%s' GROUP BY url_id) as x
                                       ON x.id2 = map_urlrating.id
                                       """ % (when, ))

        measurement["explained"] = {}
        for rating in ratings:
            measurement["total_urls"] += 1
            measurement["total_score"] += rating.rating

            if rating.rating < 200:
                measurement["green"] += 1

            if 199 < rating.rating < 1000:
                measurement["orange"] += 1

            if rating.rating > 999:
                measurement["red"] += 1

            # make stats on what kind of vulnerabilities:
            x = json.loads(rating.calculation)
            for e in x['url']['endpoints']:
                for r in e['ratings']:
                    if r['type'] not in measurement["explained"].keys():
                        measurement["explained"][r['type']] = {}
                    if r['explanation'] not in measurement["explained"][r['type']].keys():
                        measurement["explained"][r['type']][r['explanation']] = 0

                    measurement["explained"][r['type']][r['explanation']] += 1

        measurement["red percentage"] = round((measurement["red"] /
                                               measurement["total_urls"]) * 100)
        measurement["orange percentage"] = round((measurement["orange"] /
                                                  measurement["total_urls"]) * 100)
        measurement["green percentage"] = round((measurement["green"] /
                                                 measurement["total_urls"]) * 100)

        stats[stat] = measurement

    return JsonResponse({"data": stats}, json_dumps_params={'indent': 4})

@cache_page(one_day)
def wanted_urls(request):
    """
    Creates a list of organizations that have very little to none domains, and where manual
    harvesting is desired. Of course it's always desired, but this function focuses the community
    to take a closer look.

    :return:
    """

    organizations = Organization.objects.all().filter(url__is_dead=False, url__not_resolvable=False)
    organizations = organizations.annotate(n_urls=Count('url')).order_by('n_urls')[0:25]

    data = {
        "metadata": {
            "type": "WantedOrganizations",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": datetime.now(pytz.utc),
        },
        "organizations": []
    }

    organization_data = {
        "name": "",
        "type": "",
        "urls": "",
        "top_level_urls": []
    }
    import copy
    for organization in organizations:

        od = copy.copy(organization_data)
        od["name"] = organization.name
        od["type"] = organization.type.name
        od["urls"] = organization.n_urls

        topleveldomains = Url.objects.all().filter(organization=organization,
                                                   url__iregex="^[^.]*\.[^.]*$")
        for topleveldomain in topleveldomains:
            od["top_level_urls"] = []
            od["top_level_urls"].append({"url": topleveldomain.url})

        data["organizations"].append(od)

    return JsonResponse(data, json_dumps_params={'indent': 2})


@cache_page(ten_minutes)
def map_data(request, weeks_back=0):
    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    """
    Returns a json structure containing all current map data.
    This is used by the client to render the map.

    Renditions of this dataset might be pushed to github automatically.

    :return:
    """

    """
    This is left here as an artifact. With SQL you can write some great things, in one take without
    any hassle of ORM limitations. There are some damn serious limitations in Django ORM when
    it comes to simple things such as LEFT OUTER JOINS, GROUP BY, VIEW queries.

    We try to write everything in Django ORM now, but the instantly gratifying taste of how nice
    SQL is (but how terrible the differences between databases are) just keeps haunting you until
    it takes you over and just drop the entire Django ORM because of it's limitations.

    $sql = "SELECT
              url.organization as organization,
              area,
              geoJsonType,
              max(scans_ssllabs.rating) as rating
            FROM `url`
            left outer join scans_ssllabs ON url.url = scans_ssllabs.url
            left outer join organization ON url.organization = organization.name
            inner join coordinate ON coordinate.organization = organization.name
            LEFT OUTER JOIN scans_ssllabs as t2 ON (
              scans_ssllabs.url = t2.url
              AND scans_ssllabs.ipadres = t2.ipadres
              AND scans_ssllabs.poort = t2.poort
              AND t2.scanmoment > scans_ssllabs.scanmoment
              AND t2.scanmoment <= DATE_ADD(now(), INTERVAL -0 DAY))
            WHERE t2.url IS NULL
              AND url.organization <> ''
              AND scans_ssllabs.scanmoment <= DATE_ADD(now(), INTERVAL -0 DAY)
              AND url.isDead = 0
              AND scans_ssllabs.isDead = 0
            group by (area)
            order by url.organization ASC, rating DESC"

    But we also moved away from this since we want to do rating on a more general approach on one
    location. Which is far better to understand.
    """

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": "Get the code and all data from our github repo.",
        },
        "crs":
            {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features":
            [

        ]
    }

    # todo: add comment to point to github repo
    # todo: search for django server push, for instant updates sockjs?
    # Unfortunately django ORM aggregate functions only work on a single column,
    # you would think you're getting back OrganizaitonRating Objects. but thats not true.
    # http://stackoverflow.com/questions/19923877/django-orm-get-latest-for-each-group
    # http://stackoverflow.com/questions/17887075/django-orm-get-latest-record-for-group
    # This just simply doesnt work. I want a set of latest records.
    # q = OrganizationRating.objects.values('organization__name',
    #                                       'organization__type__name',
    #                                     'organization__coordinate__area',
    #                                     'organization__coordinate__geojsontype',
    #                                   'rating').aggregate(Count('organization__coordinate__area'))

    # While the star joins are a pest, we can now do nice havings and such.
    # this might be writable in Django... but the amount of time spent on it was not OK.
    # This query works in SQLite, probably also MySQL and Postgres (we'll see that in staging)
    # you can get older ratings via  WHERE `when` < '2017-03-17 16:27:00'

    cursor = connection.cursor()

    """
    A simple MySQL query like select * from x JOIN, Where, group by and having doesn't work:
    mysql has a different way of grouping: it first groups and THEN does having. While sqllite first
    does having THEn grouping. That is why in mysql all ratings where -1, because the grouping kills
    off all other records in the HAVING.

    The only way to fix that is using a subquery, unfortunately.

    Old query: select ... from . inner joins... where when <= x, group by area, having max when
    which is about 1000x slower. (new one takes about a second).

    So instead of a subquery, we ask for the latest ratings and join on this:
    SELECT DISTINCT MAX(id) FROM failmap.map_organizationrating GROUP BY organization_id;

    IN or SELECT:

    SELECT DISTINCT MAX(id) FROM failmap.map_organizationrating WHERE `when` <=
    '2017-08-14 18:21:36.984601+00:00' GROUP BY organization_id;
    """

    # original query, doesn't work in mysql due to ordering of having and group. works in sqlite
    # was extremely fast
    # sql = '''
    #  SELECT
    #         rating,
    #         organization.name,
    #         organizations_organizationtype.name,
    #         coordinate.area,
    #         coordinate.geoJsonType,
    #         organization.id
    #     FROM map_organizationrating
    #     INNER JOIN
    #       organization on organization.id = map_organizationrating.organization_id
    #     INNER JOIN
    #       organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #     INNER JOIN
    #       coordinate ON coordinate.organization_id = organization.id
    #     WHERE `when` <= '%s'
    #     GROUP BY coordinate.area
    #     HAVING MAX(`when`)
    #     ORDER BY `when` ASC'''  % (when, )

    # takes about half a second, to 0.7 seconds
    # sql = '''
    #     SELECT
    #         rating,
    #         organization.name,
    #         organizations_organizationtype.name,
    #         coordinate.area,
    #         coordinate.geoJsonType,
    #         organization.id
    #     FROM map_organizationrating
    #     INNER JOIN
    #       organization on organization.id = map_organizationrating.organization_id
    #     INNER JOIN
    #       organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #     INNER JOIN
    #       coordinate ON coordinate.organization_id = organization.id
    #     WHERE `when` = (select MAX(`when`) FROM map_organizationrating or2
    #           WHERE or2.organization_id = map_organizationrating.organization_id AND
    #           `when` <= '2017-08-14 18:21:36.984601+00:00')
    #     GROUP BY coordinate.area
    #     ORDER BY `when` ASC
    #     ''' % (when, )

    # takes 389 rows in set, 3 warnings (2 min 4.54 sec) LOL
    # sql = '''
    #     SELECT
    #         rating,
    #         organization.name,
    #         organizations_organizationtype.name,
    #         coordinate.area,
    #         coordinate.geoJsonType,
    #         organization.id
    #     FROM map_organizationrating
    #     INNER JOIN
    #       organization on organization.id = map_organizationrating.organization_id
    #     INNER JOIN
    #       organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    #     INNER JOIN
    #       coordinate ON coordinate.organization_id = organization.id
    #     WHERE map_organizationrating.id IN (
    #       SELECT DISTINCT MAX(id) FROM failmap.map_organizationrating
    #       WHERE `when` <= '%s' GROUP BY organization_id)
    #     GROUP BY coordinate.area
    #     ORDER BY `when` ASC
    #     ''' % (when, )

    # instant answer, 0.16 sec answer (mainly because of the WHEN <= date subquery.
    # This could be added to a standerd django query manager, with an extra join. It's fast.
    # sometimes 0.01 second :) And also works in sqlite. Hooray.
    sql = '''
        SELECT
            rating,
            organization.name,
            organizations_organizationtype.name,
            coordinate.area,
            coordinate.geoJsonType,
            organization.id,
            calculation
        FROM map_organizationrating
        INNER JOIN
          organization on organization.id = map_organizationrating.organization_id
        INNER JOIN
          organizations_organizationtype on organizations_organizationtype.id = organization.type_id
        INNER JOIN
          coordinate ON coordinate.organization_id = organization.id
        INNER JOIN
          (SELECT MAX(id) as id2 FROM map_organizationrating or2
          WHERE `when` <= '%s' GROUP BY organization_id) as x
          ON x.id2 = map_organizationrating.id
        GROUP BY coordinate.area
        ORDER BY `when` ASC
        ''' % (when, )
    # print(sql)
    cursor.execute(sql)

    rows = cursor.fetchall()

    # unfortunately numbered results are used.
    for i in rows:

        red = 0
        orange = 0
        green = 0

        # figure out if red, orange or green:
        calculation = json.loads(i[6])
        for url in calculation['organization']['urls']:
            if url['points'] > 999:
                red += 1
            if 199 < url['points'] < 1000:
                orange += 1
            if -1 < url['points'] < 200:
                green += 1

        dataset = {
            "type": "Feature",
            "properties":
                {
                    "OrganizationID": i[5],
                    "OrganizationType": i[2],
                    "OrganizationName": i[1],
                    "Overall": i[0],
                    "DataFrom": when,
                    "color": "red" if red else "orange" if orange else "green" if green else "gray"
                },
            "geometry":
                {
                    "type": i[4],
                    # Sometimes the data is a string, sometimes it's a list. The admin
                    # interface might influence this.
                    "coordinates":
                        json.loads(i[3]) if type(json.loads(i[3])) is list
                        else json.loads(json.loads(i[3]))  # hack :)
                }
        }

        data["features"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 4})
