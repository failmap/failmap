import collections
import logging
from datetime import datetime, timedelta

import pytz
import simplejson as json
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.contrib.syndication.views import Feed
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page

from failmap.map.models import OrganizationRating, UrlRating
from failmap.organizations.models import Coordinate, Organization, OrganizationType, Promise, Url
from failmap.scanners.models import EndpointGenericScan, TlsQualysScan

from .. import __version__
from ..app.common import JSEncoder
from ..map.models import Configuration
from .calculate import get_calculation

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
four_hours = 60 * 60 * 4
one_day = 24 * 60 * 60
ten_minutes = 60 * 10

remark = "Get the code and all data from our gitlab repo: https://gitlab.com/failmap/"


# even while this might be a bit expensive (caching helps), it still is more helpful then
# defining everything by hand.
def get_organization_type(name: str):
    try:
        return OrganizationType.objects.get(name=name).id
    except OrganizationType.DoesNotExist:
        default = Configuration.objects.all().filter(
            is_displayed=True, is_the_default_option=True
        ).order_by('display_order').values_list('organization_type__id', flat=True).first()

        return default if default else 1


# any two letters will do... :)
# All countries are managed by django-countries, but we're fine with any other weird stuff.
# url routing does validation... expect it will go wrong so STILL do validation...
def get_country(code: str):
    import re

    # handle default, save a regex
    if code in ["NL", "DE", "SE"]:
        return code

    match = re.search(r"[A-Z]{2}", code)
    if not match:
        # https://what-if.xkcd.com/53/
        return "NL"

    # check if we have a country like that in the db:
    if not Organization.objects.all().filter(country=code).exists():
        return "NL"

    return code


def get_default_country(request, ):
    country = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('country', flat=True).first()

    if not country:
        return 'NL'

    return JsonResponse([country], safe=False, encoder=JSEncoder)


def get_default_category(request, ):

    organization_type = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('organization_type__name', flat=True).first()

    if not organization_type:
        return 'municipality'
    # from config table
    return JsonResponse([organization_type], safe=False, encoder=JSEncoder)


def get_default_category_for_country(request, country: str="NL"):

    organization_type = Configuration.objects.all().filter(
        is_displayed=True,
        country=get_country(country)
    ).order_by('display_order').values_list('organization_type__name', flat=True).first()

    if not organization_type:
        return 'municipality'
    # from config table
    return JsonResponse([organization_type], safe=False, encoder=JSEncoder)


# note: this is only visual, this is no security mechanism(!) Don't act like it is.
# the data in this system is as open as possible.
def get_countries(request,):
    # sqllite doens't do distinct on, workaround

    confs = Configuration.objects.all().filter(
        is_displayed=True).order_by('display_order').values_list('country', flat=True)

    list = []
    for conf in confs:
        if conf not in list:
            list.append(conf)

    return JsonResponse(list, safe=False, encoder=JSEncoder)


def get_categories(request, country: str="NL"):

    categories = Configuration.objects.all().filter(
        country=get_country(country),
        is_displayed=True
    ).order_by('display_order').values_list('organization_type__name', flat=True)

    return JsonResponse(list(categories), safe=False, encoder=JSEncoder)


def generic_export(query, set, country: str="NL", organization_type="municipality"):
    """
    This dataset can be imported in another instance blindly using the admin interface.

    It does not export dead organizations, to save waste.

    A re-import, or existing data, will be duplicated. There is no matching algorithm yet. The first intention
    was to get you started getting an existing dataset from a certain country, and making it easy to get "up to
    speed" with another instance of this software.

    :return:
    """

    # prevent some filename manipulation trolling :)
    country = get_country(country)
    organization_type_name = OrganizationType.objects.filter(name=organization_type).values('name').first()

    if not organization_type_name:
        organization_type_name = 'municipality'
    else:
        organization_type_name = organization_type_name.get('name')

    response = JsonResponse(list(query), safe=False, encoder=JSEncoder, )
    response['Content-Disposition'] = 'attachment; filename="%s_%s_%s_%s.json"' % (
        country, organization_type_name, set, timezone.datetime.now().date())
    return response


@cache_page(one_day)
def export_urls_only(request, country: str="NL", organization_type="municipality",):
    query = Url.objects.all().filter(
        is_dead=False,
        not_resolvable=False,
        organization__is_dead=False,
        organization__country=get_country(country),
        organization__type=get_organization_type(organization_type)
    ).values_list('url', flat=True)

    return generic_export(query, 'urls_only', country, organization_type)


@cache_page(one_day)
def export_organizations(request, country: str="NL", organization_type="municipality",):
    query = Organization.objects.all().filter(
        country=get_country(country),
        type=get_organization_type(organization_type),
        is_dead=False
    ).values('id', 'name', 'type', 'wikidata', 'wikipedia', 'twitter_handle')

    return generic_export(query, 'organizations', country, organization_type)


@cache_page(one_day)
def export_organization_types(request, country: str="NL", organization_type="municipality"):
    query = OrganizationType.objects.all().values('name')
    return generic_export(query, 'organization_types', country, organization_type)


@cache_page(one_day)
def export_coordinates(request, country: str="NL", organization_type="municipality",):
    organizations = Organization.objects.all().filter(
        country=get_country(country),
        type=get_organization_type(organization_type))

    query = Coordinate.objects.all().filter(
        organization__in=list(organizations),
        is_dead=False
    ).values('id', 'organization', 'geojsontype', 'area')
    return generic_export(query, 'coordinates', country, organization_type)


@cache_page(one_day)
def export_urls(request, country: str="NL", organization_type="municipality"):
    print(country)
    query = Url.objects.all().filter(
        organization__in=Organization.objects.all().filter(
            country=get_country(country),
            type=get_organization_type(organization_type)),
        is_dead=False,
        not_resolvable=False
    ).values('id', 'url', 'organization')
    return generic_export(query, 'urls', country, organization_type)


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
        'version': __version__,
        'admin': settings.ADMIN,
        'sentry_token': settings.SENTRY_TOKEN,
    })


def d3(request):
    return render(request, 'map/d3.html')


@cache_page(one_day)
def robots_txt(request):
    return HttpResponse("User-Agent: *\nDisallow:", content_type="text/plain")


@cache_page(one_day)
def security_txt(request):
    return HttpResponse("Contact: info@internetcleanup.foundation\nEncryption: none\nAcknowledgements:",
                        content_type="text/plain")


@cache_page(one_day)
def manifest_json(request):
    # App manifest
    # https://developer.chrome.com/apps/manifest
    # https://developer.mozilla.org/en-US/docs/Web/Manifest
    manifest = {
        "name": _("Fail Map"),
        "short_name": _("Fail Map"),
        "description": _("Fail Map Introduction"),
        "version": __version__,
        "manifest_version": 3,
        "start_url": ".",
        "display": "standalone",
        "background_color": "#fff",
        "orientation": "any",
        "icons": [
            {
                "src": "static/favicons/android-icon-36x36.png",
                "sizes": "36x36",
                "type": "image/png",
                "density": "0.75"
            },
            {
                "src": "static/favicons/android-icon-48x48.png",
                "sizes": "48x48",
                "type": "image/png",
                "density": "1.0"
            },
            {
                "src": "static/favicons/android-icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "density": "1.5"
            },
            {
                "src": "static/favicons/android-icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "density": "2.0"
            },
            {
                "src": "static/favicons/android-icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "density": "3.0"
            },
            {
                "src": "static/favicons/android-icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "density": "4.0"
            }
        ],
    }
    return JsonResponse(manifest, encoder=JSEncoder)


def organizationtype_exists(request, organization_type_name):

    try:
        if OrganizationType.objects.get(name=organization_type_name).id:
            return JsonResponse({"set": True}, encoder=JSEncoder)
    except OrganizationType.DoesNotExist:
        return JsonResponse({"set": False}, encoder=JSEncoder)


@cache_page(ten_minutes)
def organization_report(request, organization_id=None, organization_name=None, weeks_back=0):
    # urls with /data/report// (two slashes)
    if not organization_id and not organization_name:
        return JsonResponse({}, safe=False, encoder=JSEncoder)

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    # getting the latest report.
    try:
        if organization_id:
            organization = Organization.objects.filter(pk=organization_id)
        elif organization_name:
            organization = Organization.objects.filter(name__iexact=organization_name)
        ratings = organization.filter(organizationrating__when__lte=when)
        values = ratings.values('organizationrating__rating',
                                'organizationrating__calculation',
                                'organizationrating__when',
                                'name',
                                'pk',
                                'twitter_handle',
                                'organizationrating__high',
                                'organizationrating__medium',
                                'organizationrating__low').latest('organizationrating__when')
    except Organization.DoesNotExist:
        report = {}
    else:
        # get the most recent non-expired 'promise'
        promise = Promise.objects.filter(organization_id=organization_id, expires_on__gt=datetime.now(pytz.utc))
        promise = promise.order_by('-expires_on')
        promise = promise.values('created_on', 'expires_on')
        promise = promise.first()

        report = {
            "name": values['name'],
            "slug": slugify(values['name']),
            "id": values['pk'],
            "twitter_handle": values['twitter_handle'],
            "rating": values['organizationrating__rating'],
            "when": values['organizationrating__when'].isoformat(),

            # fixing json being presented and escaped as a string, this makes it a lot slowr
            # had to do this cause we use jsonfield, not django_jsonfield, due to rendering map widgets in admin
            "calculation": json.loads(values['organizationrating__calculation']),
            "promise": promise,
            "high": values['organizationrating__high'],
            "medium": values['organizationrating__medium'],
            "low": values['organizationrating__low'],
        }

    return JsonResponse(report, safe=False, encoder=JSEncoder)


def string_to_delta(string_delta):
    value, unit, _ = string_delta.split()
    return timedelta(**{unit: float(value)})

# slow in sqlite, seemingly fast in mysql


@cache_page(one_day)
def terrible_urls(request, country: str="NL", organization_type="municipality", weeks_back=0):
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
            "remark": remark,
        },
        "urls":
            [

        ]
    }

    cursor = connection.cursor()

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
                url.not_resolvable,
                high,
                medium,
                low
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
              WHERE `when` <= '%(when)s' GROUP BY url_id) as x
              ON x.id2 = map_urlrating.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
            GROUP BY url.url
            HAVING(`high`) > 0
            ORDER BY `high` DESC, `medium` DESC, `low` DESC, `organization`.`name` ASC
            LIMIT 10
            ''' % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
                   "country": get_country(country)}
    # print(sql)
    cursor.execute(sql)

    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "rank": rank,
            "url": i[6],
            "organization_id": i[3],
            "organization_type": i[2],
            "organization_name": i[1],
            "organization_twitter": i[5],
            "data_from": i[4],
            "high": i[9],
            "medium": i[10],
            "low": i[11]
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["urls"].append(dataset)

    return JsonResponse(data, encoder=JSEncoder)


@cache_page(one_hour)
def top_fail(request, country: str="NL", organization_type="municipality", weeks_back=0):

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    data = {
        "metadata": {
            "type": "toplist",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": remark,
        },
        "ranking":
            [

        ]
    }

    cursor = connection.cursor()

    sql = '''
            SELECT
                rating,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle,
                high,
                medium,
                low
            FROM map_organizationrating
            INNER JOIN
              organization on organization.id = map_organizationrating.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
            INNER JOIN
              (SELECT MAX(id) as id2 FROM map_organizationrating or2
              WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
              ON x.id2 = map_organizationrating.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
            GROUP BY organization.name
            HAVING high > 0 or medium > 0
            ORDER BY `high` DESC, `medium` DESC, `medium` DESC, `organization`.`name` ASC
            LIMIT 10
            ''' % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
                   "country": get_country(country)}

    cursor.execute(sql)
    # print(sql)
    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "rank": rank,
            "organization_id": i[3],
            "organization_type": i[2],
            "organization_name": i[1],
            "organization_twitter": i[5],
            "data_from": i[4],
            "high": i[6],
            "medium": i[7],
            "low": i[8],
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, encoder=JSEncoder)


# @cache_page(cache_time)
def top_win(request, country: str="NL", organization_type="municipality", weeks_back=0):

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    data = {
        "metadata": {
            "type": "toplist",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": remark,
        },
        "ranking":
            [

        ]
    }

    cursor = connection.cursor()

    sql = '''
            SELECT
                rating,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle,
                high,
                medium,
                low
            FROM map_organizationrating
            INNER JOIN
              organization on organization.id = map_organizationrating.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
          INNER JOIN
              (SELECT MAX(id) as id2 FROM map_organizationrating or2
              WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
              ON x.id2 = map_organizationrating.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
            GROUP BY organization.name
            HAVING high = 0 AND medium = 0
            ORDER BY low ASC, LENGTH(`calculation`) DESC, `organization`.`name` ASC
            LIMIT 10
            ''' % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
                   "country": get_country(country)}
    cursor.execute(sql)

    rows = cursor.fetchall()

    rank = 1
    for i in rows:
        dataset = {
            "rank": rank,
            "organization_id": i[3],
            "organization_type": i[2],
            "organization_name": i[1],
            "organization_twitter": i[5],
            "data_from": i[4],
            "high": i[6],
            "medium": i[7],
            "low": i[8]
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, encoder=JSEncoder)


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


@cache_page(one_hour)
def stats(request, country: str="NL", organization_type="municipality", weeks_back=0):
    timeframes = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '3 weeks ago': 0,
                  '1 month ago': 0, '2 months ago': 0, '3 months ago': 0}

    for stat in timeframes:

        when = stats_determine_when(stat, weeks_back)

        measurement = {'red': 0, 'orange': 0, 'green': 0,
                       'total_organizations': 0, 'total_score': 0, 'no_rating': 0,
                       'total_urls': 0, 'red_urls': 0, 'orange_urls': 0, 'green_urls': 0,
                       'included_organizations': 0, 'endpoints': 0,
                       "endpoint": collections.OrderedDict(), "explained": {}}

        # todo: filter out dead organizations and make sure it's the correct category.
        sql = """SELECT * FROM
                   map_organizationrating
               INNER JOIN
               (SELECT MAX(id) as id2 FROM map_organizationrating or2
               WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
               ON x.id2 = map_organizationrating.id
               INNER JOIN organization ON map_organizationrating.organization_id = organization.id
               WHERE organization.type_id = '%(OrganizationTypeId)s'
               AND organization.country = '%(country)s'
               """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
                      "country": get_country(country)}

        # log.debug(sql)

        ratings = OrganizationRating.objects.raw(sql)

        noduplicates = []
        for rating in ratings:

            # do not create stats over empty organizations. That would count empty organizations.
            # you can't really filter them out above? todo: Figure that out at a next release.
            if rating.rating == -1:
                continue

            measurement["total_organizations"] += 1

            if rating.high:
                measurement["red"] += 1
            elif rating.medium:
                measurement["orange"] += 1
            else:
                measurement["green"] += 1

            # count the urls, from the latest rating. Which is very dirty :)
            # it will double the urls that are shared between organizations.
            # that is not really bad, it distorts a little.
            # we're forced to load each item separately anyway, so why not read it?
            calculation = rating.calculation
            measurement["total_urls"] += len(calculation['organization']['urls'])

            measurement["green_urls"] += sum([l['high'] == 0 and l['medium'] == 0
                                              for l in calculation['organization']['urls']])
            measurement["orange_urls"] += sum([l['high'] == 0 and l['medium'] > 0
                                               for l in calculation['organization']['urls']])
            measurement["red_urls"] += sum([l['high'] > 0 for l in calculation['organization']['urls']])

            measurement["included_organizations"] += 1

            # make some generic stats for endpoints
            for url in calculation['organization']['urls']:
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
                        if r['type'] not in measurement["explained"]:
                            measurement["explained"][r['type']] = {}
                            measurement["explained"][r['type']]['total'] = 0
                        if not r['explanation'].startswith("Repeated finding."):
                            if r['explanation'] not in measurement["explained"][r['type']]:
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
                                                               ("IPv4" if endpoint["ip_version"] == 4 else "IPv6"))
                                if endpointtype not in measurement["endpoint"]:
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

        timeframes[stat] = measurement

    return JsonResponse({"data": timeframes}, encoder=JSEncoder)


@cache_page(one_hour)
def vulnerability_graphs(request, country: str="NL", organization_type="municipality", weeks_back=0):

    # be careful these values don't overlap. While "3 weeks ago" and "1 month ago" don't seem to be overlapping,
    # they might.
    # also: it's "1 days ago", not "1 day ago".
    timeframes = [
        'now', '1 days ago', '2 days ago', '3 days ago', '4 days ago', '5 days ago', '6 days ago', '7 days ago',
        '8 days ago', '9 days ago', '10 days ago', '11 days ago', '12 days ago', '13 days ago', '14 days ago',
        '21 days ago', '28 days ago',
        '35 days ago', '42 days ago', '49 days ago', '56 days ago',
        '63 days ago', '70 days ago', '77 days ago', '84 days ago', '91 days ago']

    timeframes = reversed(timeframes)

    # if you print this, the result will be empty. WHY :)
    # print([timeframe for timeframe in timeframes])

    stats = {}
    scan_types = []

    for stat in timeframes:
        measurement = {}
        when = stats_determine_when(stat, weeks_back)
        # print("%s: %s" % (stat, when))

        # about 1 second per query, while it seems to use indexes.
        # Also moved the calculation field here also from another table, which greatly improves joins on Mysql.
        # see map_data for more info.
        sql = """SELECT map_urlrating.id as id, map_urlrating2.calculation FROM
                   map_urlrating
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
            """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
                   "country": get_country(country)}

        # print(sql)

        urlratings = UrlRating.objects.raw(sql)

        # group by vulnerability type
        for urlrating in urlratings:

            # rare occasions there are no endpoints.
            if "endpoints" not in urlrating.calculation:
                continue

            for endpoint in urlrating.calculation['endpoints']:
                for rating in endpoint['ratings']:
                    if rating['type'] not in measurement:
                        measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                    if rating['type'] not in scan_types:
                        scan_types.append(rating['type'])

                    measurement[rating['type']]['high'] += rating['high']
                    measurement[rating['type']]['medium'] += rating['medium']
                    measurement[rating['type']]['low'] += rating['low']

        for scan_type in scan_types:
            if scan_type not in stats:
                stats[scan_type] = []

        for scan_type in scan_types:
            if scan_type in measurement:
                stats[scan_type].append({'date': when.date(),
                                         'high': measurement[scan_type]['high'],
                                         'medium': measurement[scan_type]['medium'],
                                         'low': measurement[scan_type]['low'],
                                         })

    return JsonResponse(stats, encoder=JSEncoder)


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
            "remark": remark,
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

    return JsonResponse(data, encoder=JSEncoder)


@cache_page(ten_minutes)
def improvements(request, country: str="NL", organization_type: str="municipality",
                 weeks_back: int=0, weeks_duration: int=0):
    # todo: adjustable timespan
    # todo: adjustable weeks_back

    weeks_back = int(weeks_back)
    weeks_duration = int(weeks_duration)

    if not weeks_duration:
        weeks_duration = 4

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    # looks a lot like graphs, but then just subtract/add some values and done (?)

    # compare the first urlrating to the last urlrating
    # but do not include urls that don't exist.

    sql = """SELECT map_urlrating.id as id, calculation FROM
               map_urlrating
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_urlrating or2
           WHERE `when` <= '%(when)s' GROUP BY url_id) as x
           ON x.id2 = map_urlrating.id
           INNER JOIN url ON map_urlrating.url_id = url.id
           INNER JOIN url_organization on url.id = url_organization.url_id
           INNER JOIN organization ON url_organization.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    newest_urlratings = UrlRating.objects.raw(sql)

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    sql = """SELECT map_urlrating.id as id, calculation FROM
               map_urlrating
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_urlrating or2
           WHERE `when` <= '%(when)s' GROUP BY url_id) as x
           ON x.id2 = map_urlrating.id
           INNER JOIN url ON map_urlrating.url_id = url.id
           INNER JOIN url_organization on url.id = url_organization.url_id
           INNER JOIN organization ON url_organization.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when - timedelta(days=(weeks_duration * 7)),
               "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    oldest_urlratings = UrlRating.objects.raw(sql)

    old_measurement = {}
    new_measurement = {}
    scan_types = []

    # stats for the newest, should be made a function:
    for urlrating in newest_urlratings:

        if "endpoints" not in urlrating.calculation:
            continue

        for endpoint in urlrating.calculation['endpoints']:
            for rating in endpoint['ratings']:
                if rating['type'] not in new_measurement:
                    new_measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                if rating['type'] not in scan_types:
                    scan_types.append(rating['type'])

                new_measurement[rating['type']]['high'] += rating['high']
                new_measurement[rating['type']]['medium'] += rating['medium']
                new_measurement[rating['type']]['low'] += rating['low']

    # and the oldest stats, which should be the same function
    for urlrating in oldest_urlratings:

        if "endpoints" not in urlrating.calculation:
            continue

        for endpoint in urlrating.calculation['endpoints']:
            for rating in endpoint['ratings']:
                if rating['type'] not in old_measurement:
                    old_measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                if rating['type'] not in scan_types:
                    scan_types.append(rating['type'])

                old_measurement[rating['type']]['high'] += rating['high']
                old_measurement[rating['type']]['medium'] += rating['medium']
                old_measurement[rating['type']]['low'] += rating['low']

    # and now do some magic to see the changes in this timespan:
    changes = {}
    for scan_type in scan_types:
        if scan_type not in changes:
            changes[scan_type] = {}

        if scan_type not in old_measurement:
            old_measurement[scan_type] = {}

        if scan_type not in new_measurement:
            new_measurement[scan_type] = {}

        changes[scan_type] = {
            'old':
                {'date': datetime.now(pytz.utc) - timedelta(days=(weeks_duration * 7)),
                 'high': old_measurement[scan_type].get('high', 0),
                 'medium': old_measurement[scan_type].get('medium', 0),
                 'low': old_measurement[scan_type].get('low', 0),
                 },
            'new':
                {'date': when,
                 'high': new_measurement[scan_type].get('high', 0),
                 'medium': new_measurement[scan_type].get('medium', 0),
                 'low': new_measurement[scan_type].get('low', 0),
                 },
            'improvements':
                {'high': old_measurement[scan_type].get('high', 0) - new_measurement[scan_type].get('high', 0),
                 'medium': old_measurement[scan_type].get('medium', 0) - new_measurement[scan_type].get('medium', 0),
                 'low': old_measurement[scan_type].get('low', 0) - new_measurement[scan_type].get('low', 0),
                 },
        }

    # and now for overall changes, what everyone is coming for...
    for scan_type in scan_types:
        changes['overall'] = {
            'old': {
                'high': changes.get('overall', {}).get('old', {}).get('high', 0) + changes[scan_type]['old']['high'],
                'medium':
                    changes.get('overall', {}).get('old', {}).get('medium', 0) + changes[scan_type]['old']['medium'],
                'low': changes.get('overall', {}).get('old', {}).get('low', 0) + changes[scan_type]['old']['low'],
            },
            'new': {
                'high': changes.get('overall', {}).get('new', {}).get('high', 0) + changes[scan_type]['new']['high'],
                'medium':
                    changes.get('overall', {}).get('new', {}).get('medium', 0) + changes[scan_type]['new']['medium'],
                'low': changes.get('overall', {}).get('new', {}).get('low', 0) + changes[scan_type]['new']['low'],
            },
            'improvements': {
                'high': changes.get('overall', {}).get('improvements', {}).get('high', 0) +
                changes[scan_type]['improvements']['high'],
                'medium': changes.get('overall', {}).get('improvements', {}).get('medium', 0) +
                changes[scan_type]['improvements']['medium'],
                'low': changes.get('overall', {}).get('improvements', {}).get('low', 0) +
                changes[scan_type]['improvements']['low'],
            }
        }

    return JsonResponse(changes, encoder=JSEncoder, json_dumps_params={'indent': 2})


@cache_page(one_hour)
def ticker(request, country: str="NL", organization_type: str="municipality",
           weeks_back: int=0, weeks_duration: int=0):

    weeks_back = int(weeks_back)
    weeks_duration = int(weeks_duration)

    # Gives ticker data of organizations, like in news scrolling:
    # On organization level, could be on URL level in the future (selecing more cool urls?)
    # Organizations are far more meaningful.
    # Amsterdam 42 +1, 32 +2, 12 -, Zutphen 12 -3, 32 -1, 3 +3, etc.

    if not weeks_duration:
        weeks_duration = 10

    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    # looks a lot like graphs, but then just subtract/add some values and done (?)

    # compare the first urlrating to the last urlrating
    # but do not include urls that don't exist.

    # the query is INSTANT!
    sql = """SELECT map_organizationrating.id as id, name, high, medium, low FROM
               map_organizationrating
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_organizationrating or2
           WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
           ON x.id2 = map_organizationrating.id
           INNER JOIN organization ON map_organizationrating.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    newest_urlratings = list(OrganizationRating.objects.raw(sql))

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    sql = """SELECT map_organizationrating.id as id, name, high, medium, low FROM
               map_organizationrating
           INNER JOIN
           (SELECT MAX(id) as id2 FROM map_organizationrating or2
           WHERE `when` <= '%(when)s' GROUP BY organization_id) as x
           ON x.id2 = map_organizationrating.id
           INNER JOIN organization ON map_organizationrating.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when - timedelta(days=(weeks_duration * 7)),
               "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    oldest_urlratings = list(OrganizationRating.objects.raw(sql))

    changes = []
    # stats for the newest, should be made a function:

    # silently implying that both querysets have the same length and so on. Which might not be the case(?!)
    i = 0
    for newest_urlrating in newest_urlratings:

        change = {
            'organization': newest_urlrating.name,
            'high_now': newest_urlrating.high,
            'medium_now': newest_urlrating.medium,
            'low_now': newest_urlrating.low,
            'high_then': oldest_urlratings[i].high,
            'medium_then': oldest_urlratings[i].medium,
            'low_then': oldest_urlratings[i].low,
            'high_changes': newest_urlrating.high - oldest_urlratings[i].high,
            'medium_changes': newest_urlrating.medium - oldest_urlratings[i].medium,
            'low_changes': newest_urlrating.low - oldest_urlratings[i].low,
        }

        i += 1

        changes.append(change)

    return JsonResponse(changes, encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)


@cache_page(four_hours)
def map_data(request, country: str="NL", organization_type: str="municipality", weeks_back: int=0):
    if not weeks_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    """
    Returns a json structure containing all current map data.
    This is used by the client to render the map.

    Renditions of this dataset might be pushed to gitlab automatically.

    :return:
    """

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
            "remark": remark,
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

    cursor = connection.cursor()

    # instant answer, 0.16 sec answer (mainly because of the WHEN <= date subquery.
    # This could be added to a standerd django query manager, with an extra join. It's fast.
    # sometimes 0.01 second :) And also works in sqlite. Hooray.

    # ID Order should not matter, esp in async rebuild situations. It does now.

    # The calculation is being grabbed in a separate join to speed up MySQL: the calculation field is a longtext
    # that forces mysql to use disk cache as the result set is matched on to temporary tables etc.
    # So, therefore we're joining in the calculation on the last moment. Then the query just takes two seconds (still
    # slower than sqlite), but by far more acceptable than 68 seconds. This is about or3. This approach makes sqllite
    # a bit slower it seems, but still well within acceptable levels.
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
            map_organizationrating.low
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
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    # print(sql)

    # with the new solution, you only get just ONE area result per organization... -> nope, group by area :)
    cursor.execute(sql)

    rows = cursor.fetchall()

    # todo: http://www.gadzmo.com/python/using-pythons-dictcursor-in-mysql-to-return-a-dict-with-keys/
    # unfortunately numbered results are used.
    for i in rows:

        # figure out if red, orange or green:
        # #162, only make things red if there is a critical issue.
        # removed json parsing of the calculation. This saves time.
        # no contents, no endpoint ever mentioned in any url (which is a standard attribute)
        if "endpoints" not in i[6]:
            color = "gray"
        else:
            color = "red" if i[7] else "orange" if i[8] else "green"

        dataset = {
            "type": "Feature",
            "properties":
                {
                    "organization_id": i[5],
                    "organization_type": i[2],
                    "organization_name": i[1],
                    "organization_slug": slugify(i[1]),
                    "overall": i[0],
                    "high": i[7],
                    "medium": i[8],
                    "low": i[9],
                    "data_from": when,
                    "color": color
                },
            "geometry":
                {
                    "type": i[4],
                    # Sometimes the data is a string, sometimes it's a list. The admin
                    # interface might influence this.
                    "coordinates":
                        json.loads(i[3]) if isinstance(json.loads(i[3]), list)
                        else json.loads(json.loads(i[3]))  # hack :)
                }
        }

        data["features"].append(dataset)

    return JsonResponse(data, encoder=JSEncoder)


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


@cache_page(ten_minutes)
def latest_scans(request, scan_type, country: str="NL", organization_type="municipality"):
    scans = []

    dataset = {
        "scans": [],
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    if scan_type not in ["tls_qualys",
                         "Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                         "plain_https"]:
        return empty_response()

    if scan_type == "tls_qualys":
        scans = list(TlsQualysScan.objects.filter(
            endpoint__url__organization__type=get_organization_type(organization_type),
            endpoint__url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    if scan_type in ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                     "plain_https"]:
        scans = list(EndpointGenericScan.objects.filter(
            type=scan_type,
            endpoint__url__organization__type=get_organization_type(organization_type),
            endpoint__url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan in scans:
        calculation = get_calculation(scan)
        dataset["scans"].append({
            "url": scan.endpoint.url.url,
            "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
            "protocol": scan.endpoint.protocol,
            "port": scan.endpoint.port,
            "ip_version": scan.endpoint.ip_version,
            "explanation": calculation.get("explanation", ""),
            "high": calculation.get("high", 0),
            "medium": calculation.get("medium", 0),
            "low": calculation.get("low", 0),
            "last_scan_humanized": naturaltime(scan.last_scan_moment),
            "last_scan_moment": scan.last_scan_moment.isoformat()
        })

    return JsonResponse(dataset, encoder=JSEncoder)


def latest_updates(organization_id):
    """

    :param request:
    :param organization_id: the id will always be "correct", whereas name will have all kinds of terribleness:
    multiple organizations that have the same name in different branches, organizations with generic names etc.
    Finding an organization by name is tricky. Therefore ID.

    We're not filtering any further: given this might result in turning a blind eye to low or medium vulnerabilities.
    :return:
    """

    try:
        # todo: is dead etc.
        # todo: does this only do an exact match?
        organization = Organization.objects.all().filter(pk=organization_id).get()
    except ObjectDoesNotExist:
        return empty_response()

    dataset = {
        "scans": [],
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    # semi-union, given not all columns are the same. (not python/django-esque solution)
    tls_scans = list(TlsQualysScan.objects.all().filter(
        endpoint__url__organization=organization).order_by('-rating_determined_on')[0:10])
    generic_endpoint_scans = list(EndpointGenericScan.objects.filter(
        endpoint__url__organization=organization).order_by('-rating_determined_on')[0:60])

    scans = tls_scans + generic_endpoint_scans
    # todo: sort them, currently assumes the rss reader will do the sorting
    # scans = sorted(scans, key=lambda k: k.last_scan_moment, reverse=False)

    for scan in scans:
        scan_type = getattr(scan, "type", "tls_qualys")  # todo: should always be a property of scan
        calculation = get_calculation(scan)
        dataset["scans"].append({
            "organization": organization.name,
            "organization_id": organization.pk,
            "url": scan.endpoint.url.url,
            "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
            "protocol": scan.endpoint.protocol,
            "port": scan.endpoint.port,
            "ip_version": scan.endpoint.ip_version,
            "scan_type": scan_type,
            "explanation": calculation.get("explanation", ""),  # sometimes you dont get one.
            "high": calculation.get("high", 0),
            "medium": calculation.get("medium", 0),
            "low": calculation.get("low", 0),
            "rating_determined_on_humanized": naturaltime(scan.rating_determined_on),
            "rating_determined_on": scan.rating_determined_on,
            "last_scan_humanized": naturaltime(scan.last_scan_moment),
            "last_scan_moment": scan.last_scan_moment.isoformat()
        })

    return dataset


@cache_page(ten_minutes)
def updates_on_organization(request, organization_id):
    if not organization_id:
        return empty_response()

    latest_updates(organization_id)
    return JsonResponse(latest_updates(organization_id), encoder=JSEncoder)


class UpdatesOnOrganizationFeed(Feed):

    link = "/data/updates_on_organization_feed/"
    description = "Update feed."

    def title(self, organization_id):
        try:
            organization = Organization.objects.all().filter(pk=organization_id).get()
        except ObjectDoesNotExist:
            return "Organization Updates"

        return "%s Updates" % organization.name

    # it seems weird to do this.
    def get_object(self, request, *args, **kwargs):
        return kwargs['organization_id']

    # second parameter via magic
    def items(self, organization_id):
        return latest_updates(organization_id).get("scans", [])

    def item_title(self, item):
        rating = _("Perfect") if not any([item['high'], item['medium'], item['low']]) else \
            _("High") if item['high'] else _("Medium") if item['medium'] else _("Low")

        badge = "✅" if not any([item['high'], item['medium'], item['low']]) else \
            "🔴" if item['high'] else "🔶" if item['medium'] else "🍋"

        return "%s %s - %s: %s" % (badge, rating, item["url"], item["service"])

    def item_description(self, item):
        return "%s: %s" % (_(item["scan_type"]), _(item.get("explanation", "")))

    def item_pubdate(self, item):
        return item["rating_determined_on"]

    # item_link is only needed if NewsItem has no get_absolute_url method.
    # unique links are required to properly display a feed.
    def item_link(self, item):
        return "https://faalkaart.nl/#report-%s/%s/%s/%s" % \
               (item["organization_id"], item["url"], item["service"], item["rating_determined_on"])


# @cache_page(ten_minutes), you can't cache this using the decorator.
"""
Setting a parameter such as self.scan_type in the get_object will cause concurrency problems.

The manual is lacking how to get variables to the item_title and such functions: only to "items" it is somewhat
clear. This is probably because i don't know enough python. Why would this extra parameter work at the "items"
functions but not anywhere else? (signature issues).
"""


class LatestScanFeed(Feed):

    description = "Overview of the latest scans."

    # magic
    def get_object(self, request, *args, **kwargs):
        print("args: %s" % kwargs['scan_type'])
        return kwargs['scan_type']

    def title(self, scan_type):
        if scan_type:
            return "%s Scan Updates" % scan_type
        else:
            return "Vulnerabilities Feed"

    def link(self, scan_type):
        if scan_type:
            return "/data/feed/%s" % scan_type
        else:
            return "/data/feed/"

    # second parameter via magic
    def items(self, scan_type):
        print(scan_type)
        if scan_type in ["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection",
                         "plain_https"]:
            return EndpointGenericScan.objects.filter(type=scan_type).order_by('-last_scan_moment')[0:30]

        return TlsQualysScan.objects.order_by('-last_scan_moment')[0:30]

    def item_title(self, item):
        calculation = get_calculation(item)
        if not calculation:
            return ""

        rating = _("Perfect") if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            _("High") if calculation['high'] else _("Medium") if calculation['medium'] else _("Low")

        badge = "✅" if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            "🔴" if calculation['high'] else "🔶" if calculation['medium'] else "🍋"

        return "%s %s - %s" % (badge, rating, item.endpoint.url.url)

    def item_description(self, item):
        calculation = get_calculation(item)
        return _(calculation.get("explanation", ""))

    def item_pubdate(self, item):
        return item.last_scan_moment

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        return "https://faalkaart.nl/#updates/%s/%s" % (item.last_scan_moment, item.endpoint.url.url)
