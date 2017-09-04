import json
import math
from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta  # stats
from django.db import connection
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import render

from failmap_admin.map.determineratings import DetermineRatings

from .models import Organization, OrganizationRating


# Create your views here.
def index(request):
    """
    The map is simply a few files that are merged by javascript on the client side.
       We're not using the Django templating engine since it's a very poor way to develop a website.

    :param request:
    :return:
    """
    # today, used for refreshing data. / client side caching on a daily basis.
    # timestamp

    # now return the rendered template, it takes the wrong one... from another thing.
    return render(request, 'map/templates/index.html',
                  {"timestamp": datetime.now(pytz.utc),
                   "today": datetime.now(pytz.utc).date(),
                   "rendertime": "over 9000 seconds"})


# return a report for an organization. By Organization ID preferably.
def organization_report(request, organization_id):
    when = datetime.now(pytz.utc)

    # getting the latest report.
    try:
        r = Organization.objects.filter(pk=organization_id, organizationrating__when__lt=when).\
            values('organizationrating__rating',
                   'organizationrating__calculation',
                   'organizationrating__when',
                   'name',
                   'pk').order_by('-organizationrating__when')[:1].get()

        o = {"rating": r['organizationrating__rating'],
             "calculation": r['organizationrating__calculation'],
             "when": r['organizationrating__when'],
             "name": r['name'],
             "id": r['pk']}
    except Organization.DoesNotExist as e:
        o = {}

    # why not have this serializable. This is so common...
    return JsonResponse(o, json_dumps_params={'indent': 5})


def string_to_delta(string_delta):
    value, unit, _ = string_delta.split()
    return datetime.timedelta(**{unit: float(value)})


def history(request):
    # a hack to create history, when that's not done elsewhere
    # this is an ENORMOUS amount of queries. We should place this elsewhere...
    # and we should add some protections to it.
    dr = DetermineRatings()
    # 52 weeks * 2000 urls * 2 endpoints = 200.000 ratings
    dr.rate_urls(create_history=True)
    # 52 weeks * 400 organizations = 20.000 ratings
    dr.rate_organizations(create_history=True)
    return JsonResponse({}, json_dumps_params={'indent': 5})


def topfail(request, weeks_back=0):
    # todo: still no django solution for the time dimension discovered, doing a manual query... :(
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
            "remark": "LOL",
        },
        "ranking":
            [

            ]
    }

    cursor = connection.cursor()

    cursor.execute('''
        SELECT
            rating,
            organization.name,
            organizations_organizationtype.name,
            organization.id,
            `when`
        FROM map_organizationrating
        INNER JOIN
          organization on organization.id = map_organizationrating.organization_id
        INNER JOIN
          organizations_organizationtype on organizations_organizationtype.id = organization.type_id
        INNER JOIN
          coordinate ON coordinate.organization_id = organization.id
        WHERE `when` <= '%s' AND rating > 0 
        AND `when` = (select MAX(`when`) FROM map_organizationrating or2 WHERE or2.organization_id = map_organizationrating.organization_id)
        GROUP BY organization.name
        ORDER BY `rating` DESC, `organization`.`name` ASC
        LIMIT 50
        ''' % (when,))

    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "Rank": rank,
            "OrganizationID": i[3],
            "OrganizationType": i[2],
            "OrganizationName": i[1],
            "Points": i[0],
            "DataFrom": i[4]
        }
        rank = rank+1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 5})


def stats(request, weeks_back=0):
    # todo: add time dimension. Perhaps make this just a query...
    # another time dimension slicing problem. This problem just has to be solved by the community.
    # this results in hundreds of queries, where just a few would suffice normally. This is
    # becoming a problem. - this is now extremely slow, and i know exactly why (not grouping, etc).
    # 389 organizations * 7 queries. i mean... come on... what's the solution already?
    # in the meantime: caching proxies all the way down.

    # Old splitting of data, really don't know why we should do it like this, as nobody understands
    # these arbitrary numbers anyway. And the UI translating them to something useful is just a
    # waste. From now we're just delivering understandable values.
    # "0": 25,
    # "1-99": 0,
    # "100-199": 1,
    # "200-399": 40,
    # "400-999": 246,
    # "1000-4999": 74,
    # "infinite": 2,
    # "red": 322,
    # "orange": 41,
    # "green": 25,

    os = Organization.objects.all()

    stats = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '1 month ago': 0, '2 months ago': 0,
             '3 months ago': 0, '4 months ago': 0, '5 months ago': 0, '6 months ago': 0,
             'earliest': 0}

    for stat in stats:
        if stat == 'now' or stat == 'earliest':
            when = datetime.now(pytz.utc)
        else:
            value, unit, _ = stat.split()
            when = datetime.now(pytz.utc) - relativedelta(**{unit: int(value)})

        # Next to measurements in hard numbers, we also derive a conclusion in three categories:
        # red, orange and green. This is done to simplify the data, so it can be better understood.
        measurement = {'red': 0, 'orange': 0, 'green': 0,
                       'total_organizations': 0, 'total_score': 0, 'no_rating': 0}
        for o in os:
            try:

                if stat == 'earliest':
                    rating = OrganizationRating.objects.filter(organization=o)
                    rating = rating.earliest('when')
                else:
                    rating = OrganizationRating.objects.filter(organization=o, when__lte=when)
                    rating = rating.latest('when')

                measurement["total_organizations"] += 1
                measurement["total_score"] += rating.rating

                if rating.rating < 100:
                    measurement["green"] += 1

                if 99 < rating.rating < 400:
                    measurement["orange"] += 1

                if rating.rating > 399:
                    measurement["red"] += 1

            except OrganizationRating.DoesNotExist:
                measurement["total_organizations"] += 1
                measurement["total_score"] += 0
                measurement["no_rating"] += 1

        stats[stat] = measurement

    return JsonResponse({"data": stats}, json_dumps_params={'indent': 5})


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

    # todo: give this another shot in django. Perhaps it works?
    cursor = connection.cursor()

    cursor.execute('''
    SELECT
        rating,
        organization.name,
        organizations_organizationtype.name,
        coordinate.area,
        coordinate.geoJsonType,
        organization.id
    FROM map_organizationrating
    INNER JOIN
      organization on organization.id = map_organizationrating.organization_id
    INNER JOIN
      organizations_organizationtype on organizations_organizationtype.id = organization.type_id
    INNER JOIN
      coordinate ON coordinate.organization_id = organization.id
    WHERE `when` <= '%s'
    GROUP BY coordinate.area
    HAVING MAX(`when`)
    ORDER BY `when`
    ''' % (when, ))

    rows = cursor.fetchall()

    # unfortunately numbered results are used.
    for i in rows:
        dataset = {
            "type": "Feature",
            "properties":
                {
                    "OrganizationID": i[5],
                    "OrganizationType": i[2],
                    "OrganizationName": i[1],
                    "Overall": i[0],
                    "DataFrom": when
                },
            "geometry":
                {
                    "type": i[4],
                    # does whitespace change the meaning of the if? otherwise line too long...
                    "coordinates":
                        json.loads(i[3]) if type(json.loads(i[3])) is list
                        else json.loads(json.loads(i[3]))  # hack :)
                }
            }

        data["features"].append(dataset)

    return JsonResponse(data, json_dumps_params={'indent': 5})
