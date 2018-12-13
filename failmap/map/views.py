import collections
import logging
import re
from datetime import datetime, timedelta
from math import ceil

import iso3166
import pytz
import simplejson as json
from constance import config
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.contrib.syndication.views import Feed
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page
from django_celery_beat.models import PeriodicTask
from import_export.resources import modelresource_factory

from failmap import __version__
from failmap.app.common import JSEncoder
from failmap.map.calculate import get_calculation
from failmap.map.models import (Configuration, MapDataCache, OrganizationRating, UrlRating,
                                VulnerabilityStatistic)
from failmap.organizations.models import Coordinate, Organization, OrganizationType, Promise, Url
from failmap.scanners.models import EndpointGenericScan, UrlGenericScan
from failmap.scanners.types import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
four_hours = 60 * 60 * 4
one_day = 24 * 60 * 60
ten_minutes = 60 * 10

remark = "Get the code and all data from our gitlab repo: https://gitlab.com/failmap/"

# This list changes roughly every second, but that's not our problem anymore.
COUNTRIES = iso3166.countries_by_alpha2

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

    # existing countries. Yes, you can add fictional countries if you would like to, that will be handled below.
    if code in COUNTRIES:
        return code

    match = re.search(r"[A-Z]{2}", code)
    if not match:
        # https://what-if.xkcd.com/53/
        return config.PROJECT_COUNTRY

    # check if we have a country like that in the db:
    if not Organization.objects.all().filter(country=code).exists():
        return config.PROJECT_COUNTRY

    return code


def get_defaults(request, ):
    data = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values('country', 'organization_type__name').first()

    if not data:
        return JsonResponse({'country': "NL", 'layer': "municipality"}, safe=False, encoder=JSEncoder)

    return JsonResponse({'country': data['country'], 'layer': data['organization_type__name']},
                        safe=False, encoder=JSEncoder)


def get_default_country(request, ):
    country = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('country', flat=True).first()

    if not country:
        return config.PROJECT_COUNTRY

    return JsonResponse([country], safe=False, encoder=JSEncoder)


def get_default_layer(request, ):

    organization_type = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('organization_type__name', flat=True).first()

    if not organization_type:
        return 'municipality'
    # from config table
    return JsonResponse([organization_type], safe=False, encoder=JSEncoder)


def get_default_layer_for_country(request, country: str = "NL"):

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


def get_layers(request, country: str = "NL"):

    layers = Configuration.objects.all().filter(
        country=get_country(country),
        is_displayed=True
    ).order_by('display_order').values_list('organization_type__name', flat=True)

    return JsonResponse(list(layers), safe=False, encoder=JSEncoder)


def generic_export(query, set, country: str = "NL", organization_type="municipality", file_format: str = "json"):
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

    if file_format not in ['csv', 'xlsx', 'xls', 'ods', 'html', 'tsv', 'yaml', 'json']:
        file_format = 'json'

    # you can't call query.format, as it will result in parsing to that format which is expensive.
    data = {}
    if file_format == "json":
        data = query.json
    if file_format == "csv":
        # works only on complete dataset, cannot omit fields.
        data = query.json
    if file_format == "xls":
        # xls only results in empty files... so no xls support
        data = query.json
    if file_format == "xlsx":
        # cell() missing 1 required positional argument: 'column'
        # So no xslx support for now.
        data = query.json
    if file_format == "yaml":
        data = query.yaml
    if file_format == "tsv":
        # works only on complete dataset, cannot omit fields.
        data = query.json
    if file_format == "html":
        # works only on complete dataset
        data = query.json
    if file_format == "ods":
        # ods only results in empty files... so no ods support, works only on complete dataset.
        data = query.json

    response = HttpResponse(data, content_type='application/octet-stream')
    response['Content-Disposition'] = 'attachment; filename="%s_%s_%s_%s.%s"' % (
        country, organization_type_name, set, timezone.datetime.now().date(), file_format)
    return response


@cache_page(one_day)
def export_urls_only(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    query = Url.objects.all().filter(
        is_dead=False,
        not_resolvable=False,
        organization__is_dead=False,
        organization__country=get_country(country),
        organization__type=get_organization_type(organization_type)
    ).values_list('url', flat=True)

    exporter = modelresource_factory(query.model)
    dataset = exporter().export(query)

    return generic_export(dataset, 'urls_only', country, organization_type, file_format)


@cache_page(one_day)
def export_organizations(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    query = Organization.objects.all().filter(
        country=get_country(country),
        type=get_organization_type(organization_type),
        is_dead=False
    ).values('id', 'name', 'type', 'wikidata', 'wikipedia', 'twitter_handle')

    exporter = modelresource_factory(query.model)
    dataset = exporter().export(query)

    return generic_export(dataset, 'organizations', country, organization_type, file_format)


@cache_page(one_day)
def export_organization_types(request, country: str = "NL", organization_type="municipality",
                              file_format: str = "json"):
    query = OrganizationType.objects.all().values('name')
    exporter = modelresource_factory(query.model)
    dataset = exporter().export(query)
    return generic_export(dataset, 'organization_types', country, organization_type, file_format)


@cache_page(one_day)
def export_coordinates(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    organizations = Organization.objects.all().filter(
        country=get_country(country),
        type=get_organization_type(organization_type))

    query = Coordinate.objects.all().filter(
        organization__in=list(organizations),
        is_dead=False
    ).values('id', 'organization', 'geojsontype', 'area')

    exporter = modelresource_factory(query.model)
    dataset = exporter().export(query)

    return generic_export(dataset, 'coordinates', country, organization_type, file_format)


@cache_page(one_day)
def export_urls(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    query = Url.objects.all().filter(
        organization__in=Organization.objects.all().filter(
            country=get_country(country),
            type=get_organization_type(organization_type)),
        is_dead=False,
        not_resolvable=False
    ).values('id', 'url', 'organization')

    exporter = modelresource_factory(query.model)
    dataset = exporter().export(query)

    return generic_export(dataset, 'urls', country, organization_type, file_format)


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
        'country': config.PROJECT_COUNTRY,
        'debug': settings.DEBUG,
        'language': request.LANGUAGE_CODE,
        'timestamp': datetime.now(pytz.UTC).isoformat()
    })


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
def organization_report(request, country: str = "NL", organization_type="municipality",
                        organization_id=None, organization_name=None, weeks_back=0):
    # todo: check if the organization / layer is displayed on the map.
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
            organization = Organization.objects.filter(name__iexact=organization_name,
                                                       country=get_country(country),
                                                       type=get_organization_type(organization_type))
        ratings = organization.filter(organizationrating__when__lte=when)
        values = ratings.values('organizationrating__calculation',
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
def terrible_urls(request, country: str = "NL", organization_type="municipality", weeks_back=0):
    # this would only work if the latest endpoint is actually correct.
    # currently this goes wrong when the endpoints are dead but the url still resolves.
    # then there should be an url rating of 0 (as no endpoints). But we don't save that yet.
    # So this feature cannot work until the url ratings are actually correct.
    # The value of this output is not really relevant: it's a list where there are only small differences
    # and there are just a few that have a little more endpoints than the others... and those are always at the
    # top...
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
                low,
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
def top_fail(request, country: str = "NL", organization_type="municipality", weeks_back=0):

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
                low,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle,
                high,
                medium,
                low,
                total_urls,
                total_endpoints
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
            LIMIT 500
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
            "total_urls": i[9],
            "total_endpoints": i[10],
            "high_div_endpoints": "%s" % ceil((int(i[6]) / int(i[10])) * 100),
            "mid_div_endpoints": "%s" % ceil((int(i[7]) / int(i[10])) * 100),
            "low_div_endpoints": "%s" % ceil((int(i[8]) / int(i[10])) * 100),

            # Add all percentages, which is sort of an indication how bad / well the organization is doing overall.
            "relative": ceil((int(i[6]) / int(i[10])) * 1000) + ceil((int(i[7]) / int(i[10])) * 100) +
            ceil((int(i[8]) / int(i[10])) * 10)
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return JsonResponse(data, encoder=JSEncoder)


# @cache_page(cache_time)
def top_win(request, country: str = "NL", organization_type="municipality", weeks_back=0):

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
                low,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                `when`,
                organization.twitter_handle,
                high,
                medium,
                low,
                total_urls,
                total_endpoints
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
            LIMIT 500
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
            "low": i[8],
            "total_urls": i[9],
            "total_endpoints": i[10]
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

    # optimize: always give back the time 00:00:00, so the query result can be cached as the same query is
    # performed every time.
    dt = datetime(year=when.year, month=when.month, day=when.day, hour=0, minute=0, second=0, tzinfo=pytz.utc)
    # log.debug("%s: %s (%s weeks back)" % (stat, dt, weeks_back))
    return dt


@cache_page(one_hour)
def stats(request, country: str = "NL", organization_type="municipality", weeks_back=0):
    timeframes = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '3 weeks ago': 0,
                  '1 months ago': 0, '2 months ago': 0, '3 months ago': 0}

    for stat in timeframes:

        when = stats_determine_when(stat, weeks_back)

        measurement = {'red': 0, 'orange': 0, 'green': 0,
                       'total_organizations': 0, 'total_score': 0, 'no_rating': 0,
                       'total_urls': 0, 'red_urls': 0, 'orange_urls': 0, 'green_urls': 0,
                       'included_organizations': 0, 'endpoints': 0,
                       "endpoint": collections.OrderedDict(), "explained": {}}

        # todo: filter out dead organizations and make sure it's the correct layer.
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

        # django cacheops doesn't work with raw.
        # too bad https://github.com/Suor/django-cacheops
        # it's the elephant in the room in the documentation: all are explained except this one.
        # we can of course do function caching :)

        # caching for about 30 minutes.
        # But is it really set if the process is killed? Is the process killed?
        pattern = re.compile('[\W_]+')
        cache_key = pattern.sub('', "stats sql %s %s %s" % (country, organization_type, weeks_back))
        ratings = cache.get(cache_key)
        if not ratings:
            ratings = OrganizationRating.objects.raw(sql)
            cache.set(cache_key, ratings, 1800)

        noduplicates = []
        for rating in ratings:

            # do not create stats over empty organizations. That would count empty organizations.
            # you can't really filter them out above? todo: Figure that out at a next release.
            # if rating.rating == -1:
            #    continue

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
                for r in url['ratings']:
                    # stats over all different ratings
                    if r['type'] not in measurement["explained"]:
                        measurement["explained"][r['type']] = {}
                        measurement["explained"][r['type']]['total'] = 0
                    if not r['explanation'].startswith("Repeated finding."):
                        if r['explanation'] not in measurement["explained"][r['type']]:
                            measurement["explained"][r['type']][r['explanation']] = 0

                        measurement["explained"][r['type']][r['explanation']] += 1
                        measurement["explained"][r['type']]['total'] += 1

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
                                    measurement["endpoint"][endpointtype] = {'amount': 0,
                                                                             'port': endpoint["port"],
                                                                             'protocol': endpoint["protocol"],
                                                                             'ip_version': endpoint["ip_version"]}
                                measurement["endpoint"][endpointtype]['amount'] += 1
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
def organization_vulnerability_timeline(request, organization_id: int, organization_type: str = "", country: str = ""):

    # We don't do anything with organization_type: str="", country: str="", it's just so the requests are compatible
    # and easier to code.
    one_year_ago = datetime.now(pytz.utc) - timedelta(days=365)

    ratings = OrganizationRating.objects.all().filter(organization=organization_id,
                                                      when__gte=one_year_ago).order_by('when')

    stats = []

    for rating in ratings:
        stats.append({'date': rating.when.date().isoformat(),
                      'endpoints': rating.total_endpoints,
                      'urls': rating.total_urls,
                      'high': rating.url_issues_high + rating.endpoint_issues_high,
                      'medium': rating.url_issues_medium + rating.endpoint_issues_medium,
                      'low': rating.url_issues_low + rating.endpoint_issues_low})

    return JsonResponse(stats, encoder=JSEncoder, safe=False)


def organization_vulnerability_timeline_via_name(request, organization_name: str,
                                                 organization_type: str = "", country: str = ""):

    log.debug("Country: %s Layer: %s Name: %s" % (country, organization_type, organization_name))

    if not organization_type or not country:
        # getting defaults
        data = Configuration.objects.all().filter(
            is_displayed=True,
            is_the_default_option=True
        ).order_by('display_order').values('country', 'organization_type').first()

        country = data['country']
        layer = data['organization_type']
    else:
        country = get_country(code=country)
        layer = get_organization_type(name=organization_type)

    log.debug("Country: %s Layer: %s Name: %s" % (country, layer, organization_name))

    organization = Organization.objects.all().filter(country=country, type=layer,
                                                     name=organization_name,
                                                     is_dead=False).first()

    if organization:
        return organization_vulnerability_timeline(request, organization.id)
    else:
        return JsonResponse({}, encoder=JSEncoder, safe=True)


@cache_page(one_hour)
def vulnerability_graphs(request, country: str = "NL", organization_type="municipality", weeks_back=0):

    organization_type_id = get_organization_type(organization_type)
    country = get_country(country)
    when = datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))

    one_year_ago = when - timedelta(days=365)

    data = VulnerabilityStatistic.objects.all().filter(
        organization_type=organization_type_id, country=country, when__lte=when, when__gte=one_year_ago
    ).order_by('scan_type', 'when')

    """
    Desired output:
      "security_headers_x_frame_options": [
        {
          "date": "2018-07-17",
          "high": 0,
          "medium": 3950,
          "low": 0
        },
        {
          "date": "2018-07-24",
          "high": 0,
          "medium": 2940,
          "low": 0
        },
    """
    stats = {}

    for statistic in data:
        if statistic.scan_type not in stats:
            stats[statistic.scan_type] = []

        stats[statistic.scan_type].append({'high': statistic.high, 'medium': statistic.medium,
                                           'low': statistic.low, 'date': statistic.when.isoformat(),
                                           'urls': statistic.urls, 'endpoints': statistic.endpoints})

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
                                                   computed_subdomain="")
        for topleveldomain in topleveldomains:
            od["top_level_urls"] = []
            od["top_level_urls"].append({"url": topleveldomain.url})

        data["organizations"].append(od)

    return JsonResponse(data, encoder=JSEncoder)


@cache_page(ten_minutes)
def improvements(request, country: str = "NL", organization_type: str = "municipality",
                 weeks_back: int = 0, weeks_duration: int = 0):
    # todo: adjustable timespan
    # todo: adjustable weeks_back

    weeks_back = int(weeks_back)
    weeks_duration = int(weeks_duration)

    if not weeks_duration:
        weeks_duration = 1

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
def ticker(request, country: str = "NL", organization_type: str = "municipality",
           weeks_back: int = 0, weeks_duration: int = 0):

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

    # insuccesful rebuild? Or not enough organizations?
    if not oldest_urlratings:
        data = {'changes': {}, 'slogan': config.TICKER_SLOGAN}
        return JsonResponse(data, encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)

    changes = []
    # stats for the newest, should be made a function:

    # silently implying that both querysets have the same length and so on. Which might not be the case(?!)
    i = 0
    for newest_urlrating in newest_urlratings:
        if i > len(oldest_urlratings):
            # probably a failed rebuild ratings caused this situation to happen,
            # just return what we have... would that be out of sync?
            break

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

    data = {'changes': changes, 'slogan': config.TICKER_SLOGAN}

    return JsonResponse(data, encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)


def map_default(request, days_back: int = 0, displayed_issue: str = None):
    defaults = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values('country', 'organization_type__name').first()

    # On an empty database, just get the Netherlands.
    if not defaults:
        return map_data(request, "NL", "municipality", days_back, displayed_issue)

    return map_data(request, defaults['country'], defaults['organization_type__name'], days_back, displayed_issue)


# @cache_page(four_hours)
def map_data(request, country: str = "NL", organization_type: str = "municipality", days_back: int = 0,
             displayed_issue: str = None):

    data = get_map_data(country, organization_type, days_back, displayed_issue)

    return JsonResponse(data, encoder=JSEncoder)


def map_potential(request, country: str = "NL", organization_type: str = "municipality"):
    """
    Creates an overview of all organizations and regions on a certain layer. It does not have ratings or anything else.

    This has been created to see what the potential is for a certain dataset. It also shows how easy it is to show
    something on the map if you don't have to take in account filters and stacking.

    Warning: the result of this feature is SLOW. It's built to be barely good enough, not to really preview.

    :param request:
    :param country:
    :param organization_type:
    :return:
    """

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    # in this case to_attr results in a
    # 'Coordinate' object has no attribute '_iterable_class' (if you use .latest, so you cannot get the newest... :()
    # And this is also interesting: the IN query generated with prefetch on ALL organizations is optimized to be
    # one query, and that cannot work on a larger dataset. It's dangerous to use it in production at all, as the dataset
    # grows. So well, separate queries it is, again. Which is extremely slow...
    """
    Prefetch, returns this ridiculous query:
    .prefetch_related(
        Prefetch(
            "coordinate_set",
            queryset=Coordinate.objects.all().filter(is_dead=False).order_by('-created_on'),
            to_attr='coordinates'
        )
    )

    ('SELECT "coordinate"."id", "coordinate"."organization_id", '
         '"coordinate"."geoJsonType", "coordinate"."area", "coordinate"."edit_area", '
         '"coordinate"."created_on", "coordinate"."creation_metadata", '
         '"coordinate"."is_dead", "coordinate"."is_dead_since", '
         '"coordinate"."is_dead_reason" FROM "coordinate" WHERE '
         '("coordinate"."is_dead" = %s AND "coordinate"."organization_id" IN (%s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
         '%s, %s, %s, ... <trimmed 5630 bytes string>
    """
    organizations = Organization.objects.all().filter(
        country=country,
        type=organization_type,
        is_dead=False
    ).select_related('organization_type__name')

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": datetime.now(pytz.utc),
            "remark": remark,
        },
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": []
    }

    for organization in organizations:

        try:
            coordinate = Coordinate.objects.all().filter(is_dead=False, organization=organization).latest('created_on')
        except Coordinate.DoesNotExist:
            log.debug('Organization %s does not have any coordinate yet....' % organization)
            continue

        feature = {
            "type": "Feature",
            "properties":
                {
                    "organization_id": "%s" % organization.pk,
                    "organization_type": organization.type.name,
                    "organization_name": organization.name,
                    "organization_slug": slugify(organization.name),
                    "overall": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "data_from": 0,
                    "color": "green",
                    "total_urls": 0,
                    "high_urls": 0,
                    "medium_urls": 0,
                    "low_urls": 0,
                    "origin": "add_bare_url_features"
                },
            "geometry":
                {
                    "type": coordinate.geojsontype,
                    # Sometimes the data is a string, sometimes it's a list. The admin
                    # interface might influence this.
                    "coordinates": coordinate.area
                }
        }

        data["features"].append(feature)

    return JsonResponse(data, encoder=JSEncoder)


def get_map_data(country: str = "NL", organization_type: str = "municipality", days_back: int = 0,
                 displayed_issue: str = None):

    if not days_back:
        when = datetime.now(pytz.utc)
    else:
        when = datetime.now(pytz.utc) - relativedelta(days=int(days_back))

    desired_url_scans = []
    desired_endpoint_scans = []

    if displayed_issue in URL_SCAN_TYPES:
        desired_url_scans += [displayed_issue]

    if displayed_issue in ENDPOINT_SCAN_TYPES:
        desired_endpoint_scans += [displayed_issue]

    # fallback if no data, which is the default.
    if not desired_url_scans and not desired_endpoint_scans:
        desired_url_scans = URL_SCAN_TYPES
        desired_endpoint_scans = ENDPOINT_SCAN_TYPES

        # look if we have data in the cache, which will save some calculations and a slower query
        cached = MapDataCache.objects.all().filter(country=country,
                                                   organization_type=get_organization_type(organization_type),
                                                   when=when,
                                                   filters=['']).first()
    else:
        # look if we have data in the cache, which will save some calculations and a slower query
        cached = MapDataCache.objects.all().filter(country=country,
                                                   organization_type=get_organization_type(organization_type),
                                                   when=when,
                                                   filters=desired_url_scans + desired_endpoint_scans).first()

    if cached:
        return cached.dataset

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
            map_organizationrating.low,
            organization.name,
            organizations_organizationtype.name,
            coordinate_stack.area,
            coordinate_stack.geoJsonType,
            organization.id,
            or3.calculation,
            map_organizationrating.high,
            map_organizationrating.medium,
            map_organizationrating.low,
            map_organizationrating.total_issues,
            map_organizationrating.total_urls,
            map_organizationrating.high_urls,
            map_organizationrating.medium_urls,
            map_organizationrating.low_urls
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
          AND stacked_coordinate.is_dead = 1) GROUP BY organization_id) as coordinate_stack
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

    # coordinate_stack was also grouped by area, which doesn't help if there are updates: if the type of shape changes
    # then the area is selected for each type of shape (since the filter is both true for now and the past). Thus
    # removing area grouping will make sure that the share type can change without delivering double results.
    # You can test this with dutch provinces, who where imported as a different type suddenly. When loading the data
    # the map showed old and new coordinates on and off, meaning the result was semi-random somewhere. This was due to
    # area being in the stack. See change on issue #130. All maps seemed to be correct over time after this change still

    # print(sql)

    # with the new solution, you only get just ONE area result per organization... -> nope, group by area :)
    cursor.execute(sql)

    rows = cursor.fetchall()

    # todo: http://www.gadzmo.com/python/using-pythons-dictcursor-in-mysql-to-return-a-dict-with-keys/
    # unfortunately numbered results are used. There is no decent solution for sqlite and the column to dict
    # translation is somewhat hairy. A rawquery would probably be better if possible.

    for i in rows:

        # Here we're going to do something stupid: to rebuild the high, medium, low classifcation based on scan_types
        # It's somewhat insane to do it like this, but it's also insane to keep adding columns for each vulnerability
        # that's added to the system. This solution will be a bit slow, but given the caching and such it wouldn't
        # hurt too much.
        # Also: we've optimized for calculation in the past, but we're not even using it until now. So that part of
        # this code is pretty optimized :)
        # This feature is created to give an instant overview of what issues are where. This will lead more clicks to
        # reports.
        # The caching of this url should be decent, as people want to click fast. Filtering on the client
        # would be possible using the calculation field. Perhaps that should be the way. Yet then we have to do
        # filtering with javascript, which is error prone (todo: this will be done in the future, as it responds faster
        # but it will also mean an enormous increase of data sent to the client.)
        # It's actually reasonably fast.
        high, medium, low = 0, 0, 0

        calculation = json.loads(i[6])

        for url in calculation['organization']['urls']:
            for url_rating in url['ratings']:
                if url_rating['type'] in desired_url_scans and \
                        url_rating.get('comply_or_explain_valid_at_time_of_report', False) is False:
                    high += url_rating['high']
                    medium += url_rating['medium']
                    low += url_rating['low']

            # it's possible the url doesn't have ratings.
            for endpoint in url['endpoints']:
                for endpoint_rating in endpoint['ratings']:
                    if endpoint_rating['type'] in desired_endpoint_scans and \
                            endpoint_rating.get('comply_or_explain_valid_at_time_of_report', False) is False:
                        high += endpoint_rating['high']
                        medium += endpoint_rating['medium']
                        low += endpoint_rating['low']

        # figure out if red, orange or green:
        # #162, only make things red if there is a critical issue.
        # removed json parsing of the calculation. This saves time.
        # no contents, no endpoint ever mentioned in any url (which is a standard attribute)
        if "endpoints" not in i[6]:
            color = "gray"
        else:
            color = "red" if high else "orange" if medium else "yellow" if low else "green"

        dataset = {
            "type": "Feature",
            "properties":
                {
                    "organization_id": i[5],
                    "organization_type": i[2],
                    "organization_name": i[1],
                    "organization_slug": slugify(i[1]),
                    "overall": i[0],
                    "high": high,
                    "medium": medium,
                    "low": low,
                    "data_from": when,
                    "color": color,
                    "total_urls": i[11],  # = 100%
                    "high_urls": i[12],
                    "medium_urls": i[13],
                    "low_urls": i[14],
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

    # We don't try to insert the latest queryset given the website user doesn't have permission (and should not)
    # to run insert statements. Therefore a cache query here will always fail. A celery beat worker will
    # make sure the data is up to date for caching (reporting) until then loading the map is a bit slower for new
    # # queries.
    # This is what you don't need, but might write if you think of optimizing this code a bit more:
    # try:
    #     cached = MapDataCache()
    #     cached.organization_type = OrganizationType(pk=get_organization_type(organization_type))
    #     cached.country = country
    #     cached.filters = desired_url_scans + desired_endpoint_scans
    #     cached.when = when
    #     cached.dataset = data
    #     cached.save()
    # except OperationalError:
    #     # The public user does not have permission to run insert statements....

    return data


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


@cache_page(ten_minutes)
def latest_scans(request, scan_type, country: str = "NL", organization_type="municipality"):
    scans = []

    dataset = {
        "scans": [],
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    if scan_type not in ALL_SCAN_TYPES:
        return empty_response()

    if scan_type in ENDPOINT_SCAN_TYPES:
        scans = list(EndpointGenericScan.objects.filter(
            type=scan_type,
            endpoint__url__organization__type=get_organization_type(organization_type),
            endpoint__url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    if scan_type in URL_SCAN_TYPES:
        scans = list(UrlGenericScan.objects.filter(
            type=scan_type,
            url__organization__type=get_organization_type(organization_type),
            url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan in scans:
        calculation = get_calculation(scan)

        if scan_type in URL_SCAN_TYPES:
            # url scans
            dataset["scans"].append({
                "url": scan.url.url,
                "service": "%s" % scan.url.url,
                "protocol": scan_type,
                "port": "-",
                "ip_version": "-",
                "explanation": calculation.get("explanation", ""),
                "high": calculation.get("high", 0),
                "medium": calculation.get("medium", 0),
                "low": calculation.get("low", 0),
                "last_scan_humanized": naturaltime(scan.last_scan_moment),
                "last_scan_moment": scan.last_scan_moment.isoformat()
            })
        else:
            # endpoint scans
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
        # todo: check that the organization is displayed on the map
        organization = Organization.objects.all().filter(pk=organization_id).get()
    except ObjectDoesNotExist:
        return empty_response()

    dataset = {
        "scans": [],
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    # semi-union, given not all columns are the same. (not python/django-esque solution)
    generic_endpoint_scans = list(EndpointGenericScan.objects.filter(
        endpoint__url__organization=organization).order_by('-rating_determined_on')[0:60])
    url_endpoint_scans = list(UrlGenericScan.objects.filter(
        url__organization=organization).order_by('-rating_determined_on')[0:60])

    scans = generic_endpoint_scans + url_endpoint_scans

    scans = sorted(scans, key=lambda k: getattr(k, 'rating_determined_on', datetime.now(pytz.utc)), reverse=True)

    for scan in scans:
        scan_type = scan.type
        calculation = get_calculation(scan)
        if scan_type in ['DNSSEC']:
            # url scans
            dataset["scans"].append({
                "organization": organization.name,
                "organization_id": organization.pk,
                "url": scan.url.url,
                "service": "%s" % scan.url.url,
                "protocol": scan_type,
                "port": "",
                "ip_version": "",
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

        else:
            # endpoint scans
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
def explain_list(request, country, organization_type):
    """
    Because explains are possible on every scan type, try to get 10 of each, merge them and orders them chronologically

    :return:
    """
    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    ugss = UrlGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                               url__organization__country=country,
                                               url__organization__type_id=organization_type
                                               ).order_by('comply_or_explain_explained_on')[0:10]
    egss = EndpointGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                                    endpoint__url__organization__country=country,
                                                    endpoint__url__organization__type_id=organization_type
                                                    ).order_by('comply_or_explain_explained_on')[0:10]

    explains = []

    for scan in ugss:
        explains.append(get_explanation('url', scan))

    for scan in egss:
        explains.append(get_explanation('endpoint', scan))

    # sorting
    explains = sorted(explains, key=lambda k: (k['explained_on']), reverse=True)

    return JsonResponse(explains, encoder=JSEncoder, safe=False)


def export_explains(request, country, organization_type):

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    ugss = UrlGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                               url__organization__country=country,
                                               url__organization__type_id=organization_type
                                               ).order_by('comply_or_explain_explained_on')
    egss = EndpointGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                                    endpoint__url__organization__country=country,
                                                    endpoint__url__organization__type_id=organization_type
                                                    ).order_by('comply_or_explain_explained_on')

    explains = []

    for scan in ugss:
        explains.append(get_explanation('url', scan))

    for scan in egss:
        explains.append(get_explanation('endpoint', scan))

    # sorting
    explains = sorted(explains, key=lambda k: (k['explained_on']), reverse=True)

    # get the organization type name
    organization_type_name = OrganizationType.objects.filter(name=organization_type).values('name').first()

    if not organization_type_name:
        organization_type_name = 'municipality'
    else:
        organization_type_name = organization_type_name.get('name')

    response = JsonResponse(explains, safe=False, encoder=JSEncoder, )
    response['Content-Disposition'] = 'attachment; filename="%s_%s_%s_%s.json"' % (
        country, organization_type_name, set, timezone.datetime.now().date())

    return response


def get_explanation(type, scan):
    calculation = get_calculation(scan)

    explain = {
        'organizations': scan.url.organization.name if type == "url" else list(
            scan.endpoint.url.organization.all().values('id', 'name')),
        'scan_type': scan.type,
        'explanation': scan.comply_or_explain_explanation,
        'explained_by': scan.comply_or_explain_explained_by,
        'explained_on': scan.comply_or_explain_explained_on.isoformat(
        ) if scan.comply_or_explain_explained_on else datetime.now(pytz.utc).isoformat(),
        'valid_until': scan.comply_or_explain_explanation_valid_until.isoformat(),
        'original_severity': "high" if calculation['high'] else "medium" if calculation['medium'] else "low",
        'original_explanation': calculation['explanation'],
        'subject': str("%s %s/%s on IPv%s") % (
            scan.endpoint.url, scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version
        ) if type == "endpoint" else str(scan.url.url)
    }

    return explain


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
        return kwargs.get('organization_id', 0)

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
        return "%s/#report-%s/%s/%s/%s" % \
               (config.PROJECT_WEBSITE,
                item["organization_id"], item["url"], item["service"], item["rating_determined_on"])


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
        # print("args: %s" % kwargs['scan_type'])
        return kwargs.get('scan_type', '')

    def title(self, scan_type: str = ""):
        if scan_type:
            return "%s Scan Updates" % scan_type
        else:
            return "Vulnerabilities Feed"

    def link(self, scan_type: str = ""):
        if scan_type:
            return "/data/feed/%s" % scan_type
        else:
            return "/data/feed/"

    # second parameter via magic
    def items(self, scan_type):
        # print(scan_type)
        if scan_type in ENDPOINT_SCAN_TYPES:
            return EndpointGenericScan.objects.filter(type=scan_type).order_by('-last_scan_moment')[0:30]

        if scan_type in URL_SCAN_TYPES:
            return UrlGenericScan.objects.filter(type=scan_type).order_by('-last_scan_moment')[0:30]

        # have some default.
        return UrlGenericScan.objects.filter(type='DNSSEC').order_by('-last_scan_moment')[0:30]

    def item_title(self, item):
        calculation = get_calculation(item)
        if not calculation:
            return ""

        rating = _("Perfect") if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            _("High") if calculation['high'] else _("Medium") if calculation['medium'] else _("Low")

        badge = "✅" if not any([calculation['high'], calculation['medium'], calculation['low']]) else \
            "🔴" if calculation['high'] else "🔶" if calculation['medium'] else "🍋"

        if item.type in ["DNSSEC"]:
            # url generic scan:
            return "%s %s - %s" % (badge, rating, item.url.url)
        else:
            # endpoint scan
            return "%s %s - %s" % (badge, rating, item.endpoint.url.url)

    def item_description(self, item):
        calculation = get_calculation(item)
        return _(calculation.get("explanation", ""))

    def item_pubdate(self, item):
        return item.last_scan_moment

    # item_link is only needed if NewsItem has no get_absolute_url method.
    def item_link(self, item):
        if item.type in ["DNSSEC"]:
            # url generic scan:
            return "%s/#updates/%s/%s" % (config.PROJECT_WEBSITE, item.last_scan_moment, item.url.url)
        else:
            # endpoint scan
            return "%s/#updates/%s/%s" % (config.PROJECT_WEBSITE, item.last_scan_moment, item.endpoint.url.url)


def organization_autcomplete(request, country: str = "NL", organization_type="municipality", parameter: str = ""):
    # If you would try SQL injection, this would be the place. The ORM would shield it... or does it :)

    qs = Organization.objects.all()
    qs = qs.filter(type=get_organization_type(organization_type))
    qs = qs.filter(country=get_country(country))
    qs = qs.filter(name__icontains=parameter).values_list('name', flat=True)

    return JsonResponse(list(qs), encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)


def upcoming_and_past_scans(request):

    def next(obj):
        z, y = obj.schedule.is_due(last_run_at=datetime.now(pytz.utc))
        date = datetime.now(pytz.utc) + timedelta(seconds=y)
        return date

    periodic_tasks = PeriodicTask.objects.all().filter(
        enabled=True
    ).exclude(
        # Don't show system tasks that are not in the knowledge-domain of the site user.
        name__contains="celery.backend_cleanup"
    ).exclude(
        # Don't show system tasks that are not in the knowledge-domain of the site user.
        name__contains="failmap"
    ).exclude(
        # Don't show system tasks that are not in the knowledge-domain of the site user.
        name__contains="hiddden"
    ).exclude(
        # Don't show tasks that are performed extremely frequently like onboarding.
        crontab__minute__in=["*/5", "*/1", "*/10", "*/15", "*/30"]
    )
    next_scans = []  # upcoming scans
    last_scans = []  # scans performed in the past

    # get standardized task names.
    # do not add
    for periodic_task in periodic_tasks:
        scan = {}
        next_date = next(periodic_task)
        scan['name'] = mark_safe(periodic_task.name)
        scan['date'] = next_date
        scan['human_date'] = naturaltime(next_date).capitalize()
        # Tried cron_descriptor, but the text isn't as good as crontab guru.
        # the translations aren't that great, also doesn't match django locale.
        # scan['repetition'] = descripter.get_description(DescriptionTypeEnum.FULL)

        next_scans.append(scan)

    # ordering
    next_scans = sorted(next_scans, key=lambda k: k['date'], reverse=False)

    # last scans is not supportes, since celery doesn't store this information.
    data = {'next': next_scans, 'last': last_scans}
    return JsonResponse(data, encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)
