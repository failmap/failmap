import logging
from datetime import datetime, timedelta

import django_excel as excel
import iso3166
import pytz
import simplejson as json
from constance import config
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page
from django_celery_beat.models import PeriodicTask

from websecmap import __version__
from websecmap.app.common import JSEncoder
from websecmap.map.logic import datasets
from websecmap.map.logic.datasets import create_filename
from websecmap.map.logic.map import get_map_data
from websecmap.map.logic.map_defaults import get_country, get_organization_type, remark
from websecmap.map.logic.ticker import get_ticker_data
from websecmap.map.logic.top import get_top_fail_data, get_top_win_data
from websecmap.map.models import (Configuration, HighLevelStatistic, OrganizationReport,
                                  VulnerabilityStatistic)
from websecmap.organizations.models import Organization, OrganizationType, Promise, Url
from websecmap.reporting.models import UrlReport
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
four_hours = 60 * 60 * 4
one_day = 24 * 60 * 60
ten_minutes = 60 * 10


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


def generic_download(filename, data, file_type):

    supported_types = {
        'xlsx': {'content_type': "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        'ods': {'content_type': "application/vnd.oasis.opendocument.spreadsheet"},
        'csv': {'content_type': "text/csv"},
        'json': {'content_type': "text/json"},
        'mediawiki': {'content_type': "text/plain"},
        'latex': {'content_type': "text/plain"},
    }

    if file_type in supported_types:
        http_response = excel.make_response(data, file_type)
        http_response["Content-Disposition"] = "attachment; filename=%s.%s" % (slugify(filename), file_type)
        http_response["Content-type"] = supported_types[file_type]['content_type']
        return http_response

    return JsonResponse({}, encoder=JSEncoder)


@cache_page(one_day)
def export_urls_only(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    data = datasets.export_urls_only(country, organization_type)
    filename = create_filename('urls_only', country, organization_type)

    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_organizations(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    data = datasets.export_organizations(country, organization_type)
    filename = create_filename('organizations', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_organization_types(request, country: str = "NL", organization_type="municipality",
                              file_format: str = "json"):
    data = datasets.export_organization_types()
    filename = create_filename('organization_types', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_coordinates(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    data = datasets.export_coordinates(country, organization_type)
    filename = create_filename('coordinates', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_urls(request, country: str = "NL", organization_type="municipality", file_format: str = "json"):
    data = datasets.export_urls(country, organization_type)
    filename = create_filename('urls', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_hour)
def index(request):
    """
        The map is simply a few files that are merged by javascript on the client side.
        Django templating is avoided as much as possible.
    :param request:
    :return:
    """

    # save a query and a bunch of translation issues (django countries contains all countries in every language
    # so we don't have to find a javascript library to properly render...
    # the downside is that we have to run a query every load, and do less with javascript. Upside is that
    # it renders faster and easier.

    confs = Configuration.objects.all().filter(
        is_displayed=True).order_by('display_order').values_list('country', flat=True)

    inital_countries = []
    for conf in confs:
        if conf not in inital_countries:
            inital_countries.append(conf)

    return render(request, 'map/index.html', {
        'version': __version__,
        'admin': settings.ADMIN,
        'sentry_token': settings.SENTRY_TOKEN,
        'country': config.PROJECT_COUNTRY,
        'debug': settings.DEBUG,
        'language': request.LANGUAGE_CODE,
        'timestamp': datetime.now(pytz.UTC).isoformat(),
        'initial_map_data_url': '',
        'initial_countries': inital_countries,
        'number_of_countries': len(inital_countries)
    })


def map_only(request, country: str = "NL", organization_type: str = "municipality", days_back: int = 0,
             displayed_issue: str = None):

    # build an initial data URL, which overrides the standard default data url for the map.

    country = "NL" if country not in iso3166.countries_by_alpha2 else country

    initial_map_data_url = "/data/map/%s/%s/%s/%s/" % (country, organization_type, days_back, displayed_issue)

    return render(request, 'map/map_only.html', {
        'version': __version__,
        'admin': settings.ADMIN,
        'sentry_token': settings.SENTRY_TOKEN,
        'country': config.PROJECT_COUNTRY,
        'debug': settings.DEBUG,
        'language': request.LANGUAGE_CODE,
        'timestamp': datetime.now(pytz.UTC).isoformat(),
        'initial_map_data_url': initial_map_data_url
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
        "name": _("Site Title"),
        "short_name": _("Site Title"),
        "description": _("Introduction"),
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
        ratings = organization.filter(organizationreport__when__lte=when)
        values = ratings.values('organizationreport__calculation',
                                'organizationreport__when',
                                'name',
                                'pk',
                                'twitter_handle',
                                'organizationreport__high',
                                'organizationreport__medium',
                                'organizationreport__low').latest('organizationreport__when')
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
            "when": values['organizationreport__when'].isoformat(),

            # fixing json being presented and escaped as a string, this makes it a lot slowr
            # had to do this cause we use jsonfield, not django_jsonfield, due to rendering map widgets in admin
            "calculation": json.loads(values['organizationreport__calculation']),
            "promise": promise,
            "high": values['organizationreport__high'],
            "medium": values['organizationreport__medium'],
            "low": values['organizationreport__low'],
        }

    return JsonResponse(report, safe=False, encoder=JSEncoder)


def string_to_delta(string_delta):
    value, unit, _ = string_delta.split()
    return timedelta(**{unit: float(value)})


@cache_page(one_hour)
def top_fail(request, country: str = "NL", organization_type="municipality", weeks_back=0):
    data = get_top_fail_data(country, organization_type, weeks_back)
    return JsonResponse(data, encoder=JSEncoder)


@cache_page(one_hour)
def top_win(request, country: str = "NL", organization_type="municipality", weeks_back=0):
    data = get_top_win_data(country, organization_type, weeks_back)
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

    when = []
    for stat in timeframes:
        when.append(stats_determine_when(stat, weeks_back).date())

    stats = HighLevelStatistic.objects.all().filter(
        country=country,
        organization_type=get_organization_type(organization_type),
        when__in=when
    )

    # todo: apply the label of the timeframe in the report result.
    reports = {}
    for idx, stat in enumerate(timeframes):
        reports[stat] = stats[idx].report

    return JsonResponse({"data": reports}, encoder=JSEncoder)


@cache_page(one_hour)
def organization_vulnerability_timeline(request, organization_id: int, organization_type: str = "", country: str = ""):

    # We don't do anything with organization_type: str="", country: str="", it's just so the requests are compatible
    # and easier to code.
    one_year_ago = datetime.now(pytz.utc) - timedelta(days=365)

    ratings = OrganizationReport.objects.all().filter(organization=organization_id,
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
                                           'urls': statistic.urls, 'ok_urls': statistic.ok_urls,
                                           'endpoints': statistic.endpoints, 'ok_endpoints': statistic.ok_endpoints,
                                           'ok': statistic.ok
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

    sql = """SELECT reporting_urlreport.id as id, calculation FROM
               reporting_urlreport
           INNER JOIN
           (SELECT MAX(id) as id2 FROM reporting_urlreport or2
           WHERE `when` <= '%(when)s' GROUP BY url_id) as x
           ON x.id2 = reporting_urlreport.id
           INNER JOIN url ON reporting_urlreport.url_id = url.id
           INNER JOIN url_organization on url.id = url_organization.url_id
           INNER JOIN organization ON url_organization.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    newest_urlratings = UrlReport.objects.raw(sql)

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    sql = """SELECT reporting_urlreport.id as id, calculation FROM
               reporting_urlreport
           INNER JOIN
           (SELECT MAX(id) as id2 FROM reporting_urlreport or2
           WHERE `when` <= '%(when)s' GROUP BY url_id) as x
           ON x.id2 = reporting_urlreport.id
           INNER JOIN url ON reporting_urlreport.url_id = url.id
           INNER JOIN url_organization on url.id = url_organization.url_id
           INNER JOIN organization ON url_organization.organization_id = organization.id
            WHERE organization.type_id = '%(OrganizationTypeId)s'
            AND organization.country = '%(country)s'
        """ % {"when": when - timedelta(days=(weeks_duration * 7)),
               "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    oldest_urlratings = UrlReport.objects.raw(sql)

    old_measurement = {}
    new_measurement = {}
    scan_types = []

    # stats for the newest, should be made a function:
    for urlrating in newest_urlratings:

        # url level, why are there reports without url ratings / empty url ratings like
        if 'ratings' in urlrating.calculation:
            for rating in urlrating.calculation['ratings']:
                if rating['type'] not in new_measurement:
                    new_measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                if rating['type'] not in scan_types:
                    scan_types.append(rating['type'])

                new_measurement[rating['type']]['high'] += rating['high']
                new_measurement[rating['type']]['medium'] += rating['medium']
                new_measurement[rating['type']]['low'] += rating['low']

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

        if 'ratings' in urlrating.calculation:
            for rating in urlrating.calculation['ratings']:
                if rating['type'] not in old_measurement:
                    old_measurement[rating['type']] = {'high': 0, 'medium': 0, 'low': 0}

                if rating['type'] not in scan_types:
                    scan_types.append(rating['type'])

                old_measurement[rating['type']]['high'] += rating['high']
                old_measurement[rating['type']]['medium'] += rating['medium']
                old_measurement[rating['type']]['low'] += rating['low']

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

    data = get_ticker_data(country, organization_type, weeks_back, weeks_duration)

    return JsonResponse(data, encoder=JSEncoder, json_dumps_params={'indent': 2}, safe=False)


def map_default(request, days_back: int = 0, displayed_issue: str = "all"):
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
             displayed_issue: str = "all"):

    data = get_map_data(country, organization_type, days_back, displayed_issue)

    return JsonResponse(data, encoder=JSEncoder)


@cache_page(ten_minutes)
def all_latest_scans(request, country: str = "NL", organization_type="municipality"):
    scans = {}

    dataset = {
        "scans": {},
        "render_date": datetime.now(pytz.utc).isoformat(),
        "remark": remark,
    }

    for scan_type in ENDPOINT_SCAN_TYPES:
        scans[scan_type] = list(EndpointGenericScan.objects.filter(
            type=scan_type,
            endpoint__url__organization__type=get_organization_type(organization_type),
            endpoint__url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan_type in URL_SCAN_TYPES:
        scans[scan_type] = list(UrlGenericScan.objects.filter(
            type=scan_type,
            url__organization__type=get_organization_type(organization_type),
            url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan_type in ALL_SCAN_TYPES:

        dataset["scans"][scan_type] = []

        for scan in scans[scan_type]:
            calculation = get_severity(scan)

            if scan_type in URL_SCAN_TYPES:
                # url scans
                dataset["scans"][scan_type].append({
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
                dataset["scans"][scan_type].append({
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
        endpoint__url__organization=organization,
        type__in=ENDPOINT_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:60])
    url_endpoint_scans = list(UrlGenericScan.objects.filter(
        url__organization=organization,
        type__in=URL_SCAN_TYPES
    ).order_by('-rating_determined_on')[0:60])

    scans = generic_endpoint_scans + url_endpoint_scans

    scans = sorted(scans, key=lambda k: getattr(k, 'rating_determined_on', datetime.now(pytz.utc)), reverse=True)

    for scan in scans:
        scan_type = scan.type
        calculation = get_severity(scan)
        if scan_type in URL_SCAN_TYPES:
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
    calculation = get_severity(scan)

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

    return JsonResponse(latest_updates(organization_id), encoder=JSEncoder)


# @cache_page(ten_minutes), you can't cache this using the decorator.
"""
Setting a parameter such as self.scan_type in the get_object will cause concurrency problems.

The manual is lacking how to get variables to the item_title and such functions: only to "items" it is somewhat
clear. This is probably because i don't know enough python. Why would this extra parameter work at the "items"
functions but not anywhere else? (signature issues).
"""


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
