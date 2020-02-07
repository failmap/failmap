import json
import logging
from datetime import datetime
from wsgiref.util import FileWrapper

import django_excel as excel
import pytz
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.text import slugify
from django.utils.translation import ugettext as _
from django.views.decorators.cache import cache_page

from websecmap import __version__
from websecmap.app.common import JSEncoder
from websecmap.app.constance import get_bulk_values
from websecmap.map.logic import datasets
from websecmap.map.logic.admin import (add_organization, add_proxies, add_urls,
                                       switch_lattitude_and_longitude, user_is_staff_member)
from websecmap.map.logic.datasets import create_filename
from websecmap.map.logic.explain import (explain, get_all_explains, get_recent_explains,
                                         remove_explanation)
from websecmap.map.logic.improvements import get_improvements
from websecmap.map.logic.latest import get_all_latest_scans
from websecmap.map.logic.map import get_map_data
from websecmap.map.logic.map_defaults import (DEFAULT_COUNTRY, DEFAULT_LAYER, get_country,
                                              get_defaults, get_initial_countries, get_layers,
                                              get_organization_type)
from websecmap.map.logic.organization_report import (get_organization_report_by_id,
                                                     get_organization_report_by_name)
from websecmap.map.logic.rss_feeds import latest_updates
from websecmap.map.logic.stats_and_graphs import (get_organization_vulnerability_timeline,
                                                  get_organization_vulnerability_timeline_via_name,
                                                  get_stats, get_vulnerability_graph)
from websecmap.map.logic.ticker import get_ticker_data
from websecmap.map.logic.top import get_top_fail_data, get_top_win_data
from websecmap.map.logic.upcoming_scans import get_next_and_last_scans
from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization
from websecmap.scanners.models import Screenshot

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
four_hours = 60 * 60 * 4
one_day = 24 * 60 * 60
ten_minutes = 60 * 10

DEFAULT_FILE_FORMAT = 'json'


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


def defaults(request):
    return JsonResponse(get_defaults(), encoder=JSEncoder, safe=False)


def layers(request, country):
    return JsonResponse(get_layers(country), encoder=JSEncoder, safe=False)


@cache_page(one_day)
def export_urls_only(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                     file_format: str = DEFAULT_FILE_FORMAT):
    data = datasets.export_urls_only(country, organization_type)
    filename = create_filename('urls_only', country, organization_type)

    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_organizations(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                         file_format: str = DEFAULT_FILE_FORMAT):
    data = datasets.export_organizations(country, organization_type)
    filename = create_filename('organizations', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_organization_types(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                              file_format: str = DEFAULT_FILE_FORMAT):
    data = datasets.export_organization_types()
    filename = create_filename('organization_types', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_coordinates(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                       file_format: str = DEFAULT_FILE_FORMAT):
    data = datasets.export_coordinates(country, organization_type)
    filename = create_filename('coordinates', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_day)
def export_urls(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                file_format: str = DEFAULT_FILE_FORMAT):
    data = datasets.export_urls(country, organization_type)
    filename = create_filename('urls', country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(one_hour)
def export_explains(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                    file_format: str = DEFAULT_FILE_FORMAT):
    # we cannot use the queryset, as explains are two querysets (or a complex query)
    # so we currently offer json in any case, even if the site says otherwise.
    data = get_all_explains(country, organization_type)
    filename = create_filename('explains', country, organization_type)
    response = JsonResponse(data, safe=False, encoder=JSEncoder, )
    response['Content-Disposition'] = 'attachment; filename="%s.json"' % filename
    return response


def inject_default_language_cookie(request, response) -> HttpResponse:
    # If you visit any of the main pages, this is set to the desired language your browser emits.
    # This synchronizes the language between javascript (OS language) and browser (Accept Language).
    if 'preferred_language' not in request.COOKIES:
        # Get the accept language,
        # Add the cookie to render.
        accept_language = request.LANGUAGE_CODE
        response.set_cookie(key='preferred_language', value=accept_language)

    return response


def emptypage(request):
    return render(request, 'map/empty.html')


@cache_page(one_hour)
def index(request, map_configuration=None):

    def countries_and_layers():
        confs = Configuration.objects.all().filter(
            is_displayed=True
        ).order_by('display_order')

        # returns this, translated according to the preferred locale, this should be JS in the future:
        countries = {
            'EN': {
                'name': "",
                'flag': "",
                'code': "EN",
                'layers': [],
            },
        }

        # use django countries to augment this infromation based on the current prefered language,
        # which unfortunately doesn't change when switching language, but ok... for now it's fine.
        countries = {}
        for conf in confs:
            if conf.country.code not in countries:
                countries = {**countries, **{conf.country.code: {
                    'code': conf.country.code,
                    'name': conf.country.name,
                    'flag': conf.country.flag,
                    'layers': [conf.organization_type.name]}
                }}
            else:
                countries[conf.country]['layers'].append(conf.organization_type.name)

        return countries

    initial_countries = get_initial_countries()

    if map_configuration:
        map_defaults = {'country': map_configuration.country, 'layer': map_configuration.organization_type.name}
    else:
        map_defaults = get_defaults()

    # instead of asking for every config variable, get all of them in one go
    config = get_bulk_values([
        "PROJECT_COUNTRY",
        "PROJECT_NAME",
        "PROJECT_TAGLINE",
        "SHOW_INTRO",
        "SHOW_CHARTS",
        "SHOW_COMPLY_OR_EXPLAIN",
        "SHOW_SCAN_SCHEDULE",
        "SHOW_DATASETS",
        "SHOW_ANNOUNCEMENT",
        "SHOW_EXTENSIVE_STATISTICS",
        "SHOW_STATS_NUMBERS",
        "SHOW_STATS_IMPROVEMENTS",
        "SHOW_STATS_GRAPHS",
        "SHOW_STATS_CHANGES",
        "SHOW_TICKER",
        "SHOW_SERVICES",
        "SHOW_FTP",
        "SHOW_PLAIN_HTTPS",
        "SHOW_DNSSEC",
        "SHOW_HTTP_SECURITY_HEADER_STRICT_TRANSPORT_SECURITY",
        "SHOW_HTTP_SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS",
        "SHOW_HTTP_SECURITY_HEADER_X_FRAME_OPTIONS",
        "SHOW_HTTP_SECURITY_HEADER_X_XSS_PROTECTION",
        "SHOW_TLS_QUALYS_CERTIFICATE_TRUSTED",
        "SHOW_TLS_QUALYS_ENCRYPTION_QUALITY",
        "SHOW_INTERNET_NL_MAIL_STARTTLS_TLS_AVAILABLE",
        "SHOW_INTERNET_NL_MAIL_AUTH_SPF_EXIST",
        "SHOW_INTERNET_NL_MAIL_AUTH_DKIM_EXIST",
        "SHOW_INTERNET_NL_MAIL_AUTH_DMARC_EXIST",
        "RESPONSIBLE_ORGANIZATION_NAME",
        "RESPONSIBLE_ORGANIZATION_PROMO_TEXT",
        "RESPONSIBLE_ORGANIZATION_WEBSITE",
        "RESPONSIBLE_ORGANIZATION_MAIL",
        "RESPONSIBLE_ORGANIZATION_TWITTER",
        "RESPONSIBLE_ORGANIZATION_FACEBOOK",
        "RESPONSIBLE_ORGANIZATION_LINKEDIN",
        "RESPONSIBLE_ORGANIZATION_WHATSAPP",
        "RESPONSIBLE_ORGANIZATION_PHONE",
        "PROJECT_NAME",
        "PROJECT_TAGLINE",
        "PROJECT_COUNTRY",
        "PROJECT_MAIL",
        "PROJECT_ISSUE_MAIL",
        "PROJECT_TWITTER",
        "PROJECT_FACEBOOK",
        "COMPLY_OR_EXPLAIN_DISCUSSION_FORUM_LINK",
        "COMPLY_OR_EXPLAIN_EMAIL_ADDRESS",
        "MAPBOX_ACCESS_TOKEN",
        "GITTER_CHAT_ENABLE",
        "GITTER_CHAT_CHANNEL",
        "ANNOUNCEMENT",
    ])

    # a number of variables are injected so they can be used inside javascript.
    return inject_default_language_cookie(request, render(request, 'map/index.html', {
        'configuration': config,
        'version': __version__,
        'admin': settings.ADMIN,
        'sentry_token': settings.SENTRY_TOKEN,
        'country': config['PROJECT_COUNTRY'],
        'debug': True if settings.DEBUG else False,
        'language': request.LANGUAGE_CODE,
        'timestamp': datetime.now(pytz.UTC).isoformat(),
        'initial_map_data_url': '',
        'initial_countries': initial_countries,
        'countries_and_layers': countries_and_layers(),
        'default_country': map_defaults['country'],
        'default_layer': map_defaults['layer'],
        'default_week': 0,
        'number_of_countries': len(initial_countries),
        'initial_map_data': get_map_data(map_defaults['country'], map_defaults['layer'], 0, ''),
    }))


@cache_page(one_day)
def robots_txt(request):
    return render(request, 'map/robots.txt', content_type="text/plain")


@cache_page(one_day)
def security_txt(request):
    return render(request, 'map/security.txt', content_type="text/plain")


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


@cache_page(one_hour)
def organization_report_by_id(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER,
                              organization_id=None, weeks_back=0):
    if not organization_id:
        return empty_response()

    report = get_organization_report_by_id(organization_id, weeks_back)
    return JsonResponse(report, safe=False, encoder=JSEncoder)


@cache_page(one_hour)
def organization_report_by_name(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER,
                                organization_name=None, weeks_back=0):
    if not (organization_name and country and organization_type):
        return empty_response()

    report = get_organization_report_by_name(
        organization_name=organization_name, country=country, organization_type=organization_type,
        weeks_back=weeks_back)
    return JsonResponse(report, safe=False, encoder=JSEncoder)


@cache_page(one_hour)
def top_fail(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, weeks_back=0):
    data = get_top_fail_data(country, organization_type, weeks_back)
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(one_hour)
def top_win(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, weeks_back=0):
    data = get_top_win_data(country, organization_type, weeks_back)
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(one_hour)
def stats(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, weeks_back=0):
    reports = get_stats(country, organization_type, weeks_back)
    return JsonResponse(reports, encoder=JSEncoder)


@cache_page(one_hour)
def organization_vulnerability_timeline(request, organization_id: int, organization_type: str = "", country: str = ""):
    stats = get_organization_vulnerability_timeline(organization_id)
    return JsonResponse(stats, encoder=JSEncoder, safe=False)


@cache_page(one_hour)
def organization_vulnerability_timeline_via_name(request, organization_name: str,
                                                 organization_type: str = "", country: str = ""):
    stats = get_organization_vulnerability_timeline_via_name(organization_name, organization_type, country)
    return JsonResponse(stats, encoder=JSEncoder, safe=False)


@cache_page(one_hour)
def vulnerability_graphs(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, weeks_back=0):
    stats = get_vulnerability_graph(country, organization_type, weeks_back)
    return JsonResponse(stats, encoder=JSEncoder)


@cache_page(ten_minutes)
def improvements(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER,
                 weeks_back: int = 0, weeks_duration: int = 0):

    changes = get_improvements(country, organization_type, weeks_back, weeks_duration)
    return JsonResponse(changes, encoder=JSEncoder)


@cache_page(one_hour)
def ticker(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER,
           weeks_back: int = 0, weeks_duration: int = 0):

    data = get_ticker_data(country, organization_type, weeks_back, weeks_duration)
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(four_hours)
def map_default(request, days_back: int = 0, displayed_issue: str = "all"):

    defaults = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values('country', 'organization_type__name').first()

    # On an empty database, just get the Netherlands.
    if not defaults:
        return map_data(request, DEFAULT_COUNTRY, DEFAULT_LAYER, days_back, displayed_issue)

    return map_data(request, defaults['country'], defaults['organization_type__name'], days_back, displayed_issue)


@cache_page(one_hour)
def organization_list(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER):
    query = Organization.objects.all().filter(
        country=get_country(country),
        type=get_organization_type(organization_type),
        is_dead=False
    ).values_list(
        'id', 'name', 'computed_name_slug',
    )

    data = [{'id': elem[0], 'name': elem[1], 'slug': elem[2]} for elem in query]

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(four_hours)
def map_data(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER, days_back: int = 0,
             displayed_issue: str = "all"):

    data = get_map_data(country, organization_type, days_back, displayed_issue)

    return JsonResponse(data, encoder=JSEncoder)


@cache_page(ten_minutes)
def all_latest_scans(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER):
    dataset = get_all_latest_scans(country, organization_type)
    return JsonResponse(dataset, encoder=JSEncoder)


@cache_page(ten_minutes)
def explain_list(request, country, organization_type):
    data = get_recent_explains(country, organization_type)
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(ten_minutes)
def updates_on_organization(request, organization_id):
    if not organization_id:
        return empty_response()

    return JsonResponse(latest_updates(organization_id), encoder=JSEncoder)


def organization_autcomplete(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                             parameter: str = ""):
    # See Django Auto Complete for more info.
    qs = Organization.objects.all()
    qs = qs.filter(type=get_organization_type(organization_type))
    qs = qs.filter(country=get_country(country))
    qs = qs.filter(name__icontains=parameter).values_list('name', flat=True)

    return JsonResponse(list(qs), encoder=JSEncoder, safe=False)


@cache_page(ten_minutes)
def upcoming_and_past_scans(request):
    data = get_next_and_last_scans()
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(one_day)
def screenshot(request, endpoint_id=0):
    # get the latest screenshot from an endpoint.

    screenshot = Screenshot.objects.all().filter(endpoint=endpoint_id).order_by('-created_on').first()

    if not screenshot:
        return HttpResponse()

    if not screenshot.image:
        return HttpResponse()

    wrapper = FileWrapper(screenshot.image.file.open('rb'))
    response = HttpResponse(wrapper, content_type="image/PNG")
    return response


def get_json_body(request):

    try:
        user_input = json.loads(request.body)
    except json.JSONDecodeError:
        user_input = {}

    return user_input


def _explain(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, encoder=JSEncoder, safe=False)

    request = get_json_body(request)

    data = explain(request.get('scan_id'), request.get('scan_type'),
                   request.get('explanation'), request.get('explained_by'), request.get('validity'))

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def _remove_explain(request):
    request = get_json_body(request)
    data = remove_explanation(request.get('scan_id'), request.get('scan_type'))
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def _add_urls(request):
    request = get_json_body(request)
    data = add_urls(request.get('organization_id'), request.get('urls'))
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def _add_proxies(request):
    request = get_json_body(request)
    data = add_proxies(request.get('proxies'))
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def _switch_lattitude_and_longitude(request, organization_id=0):
    return JsonResponse(switch_lattitude_and_longitude(organization_id), encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def _add_organization(request):
    request = get_json_body(request)
    return JsonResponse(add_organization(request), encoder=JSEncoder, safe=False)
