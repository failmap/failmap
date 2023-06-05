import json
import logging
from datetime import date, datetime, timezone
from wsgiref.util import FileWrapper

import django_excel as excel
import orjson
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page

from websecmap import __version__
from websecmap.app.common import JSEncoder
from websecmap.app.constance import constance_cached_value, get_all_values, get_bulk_values
from websecmap.map.logic import datasets
from websecmap.map.logic.admin import (
    add_organization,
    add_proxies,
    add_urls,
    delete_coordinate,
    move_coordinate,
    switch_lattitude_and_longitude,
    user_is_staff_member,
)
from websecmap.map.logic.datasets import create_filename
from websecmap.map.logic.explain import explain, get_all_explains, get_recent_explains, remove_explanation
from websecmap.map.logic.improvements import get_improvements
from websecmap.map.logic.latest import get_all_latest_scans
from websecmap.map.logic.login_plaza import get_products, login_plaza_data
from websecmap.map.logic.map import get_map_data
from websecmap.map.logic.map_defaults import (
    DEFAULT_COUNTRY,
    DEFAULT_LAYER,
    get_country,
    get_defaults,
    get_initial_countries,
    get_layers,
    get_organization_type,
)
from websecmap.map.logic.map_health import get_lastest_map_health_data
from websecmap.map.logic.organization_report import get_organization_report_by_id, get_organization_report_by_name
from websecmap.map.logic.rss_feeds import latest_updates
from websecmap.map.logic.stats_and_graphs import (
    get_organization_vulnerability_timeline,
    get_organization_vulnerability_timeline_via_name,
    get_short_and_simple_stats,
    get_stats,
    get_vulnerability_graph,
    what_to_improve,
)
from websecmap.map.logic.ticker import get_ticker_data
from websecmap.map.logic.top import get_top_fail_data, get_top_win_data
from websecmap.map.logic.upcoming_scans import get_next_and_last_scans
from websecmap.map.models import Configuration, LandingPage, OrganizationReport
from websecmap.organizations.models import Organization
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Screenshot
from websecmap.scanners.scanmetadata import get_backend_scanmetadata, get_scanners_for_frontend

log = logging.getLogger(__package__)

ONE_MINUTE = 60
ONE_HOUR = 60 * 60
FOUR_HOURS = 60 * 60 * 4
ONE_DAY = 24 * 60 * 60
TEN_MINUTES = 60 * 10

DEFAULT_FILE_FORMAT = "json"


def json_response(data: dict) -> HttpResponse:
    return HttpResponse(orjson.dumps(data), content_type="text/json", status=200)


def empty_response():
    return JsonResponse({}, encoder=JSEncoder)


def generic_download(filename, data, file_type):
    supported_types = {
        "xlsx": {"content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        "ods": {"content_type": "application/vnd.oasis.opendocument.spreadsheet"},
        "csv": {"content_type": "text/csv"},
        "json": {"content_type": "text/json"},
        "mediawiki": {"content_type": "text/plain"},
        "latex": {"content_type": "text/plain"},
    }

    if file_type in supported_types:
        http_response = excel.make_response(data, file_type)
        http_response["Content-Disposition"] = f"attachment; filename={slugify(filename)}.{file_type}"
        http_response["Content-type"] = supported_types[file_type]["content_type"]
        return http_response

    return JsonResponse({}, encoder=JSEncoder)


def defaults(request):
    return JsonResponse(get_defaults(), encoder=JSEncoder, safe=False)


def layers(request, country):
    return JsonResponse(get_layers(country), encoder=JSEncoder, safe=False)


@cache_page(TEN_MINUTES)
def export_urls_only(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    data = datasets.export_urls_only(country, organization_type)
    filename = create_filename("urls_only", country, organization_type)

    return generic_download(filename, data, file_format)


@cache_page(TEN_MINUTES)
def export_organizations(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    data = datasets.export_organizations(country, organization_type)
    filename = create_filename("organizations", country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(TEN_MINUTES)
def export_organization_types(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    data = datasets.export_organization_types()
    filename = create_filename("organization_types", country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(TEN_MINUTES)
def export_coordinates(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    data = datasets.export_coordinates(country, organization_type)
    filename = create_filename("coordinates", country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(TEN_MINUTES)
def export_urls(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    data = datasets.export_urls(country, organization_type)
    filename = create_filename("urls", country, organization_type)
    return generic_download(filename, data, file_format)


@cache_page(TEN_MINUTES)
def export_explains(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, file_format: str = DEFAULT_FILE_FORMAT
):
    # we cannot use the queryset, as explains are two querysets (or a complex query)
    # so we currently offer json in any case, even if the site says otherwise.
    data = get_all_explains(country, organization_type)
    filename = create_filename("explains", country, organization_type)
    response = JsonResponse(
        data,
        safe=False,
        encoder=JSEncoder,
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
    return response


def inject_default_language_cookie(request, response) -> HttpResponse:
    # If you visit any of the main pages, this is set to the desired language your browser emits.
    # This synchronizes the language between javascript (OS language) and browser (Accept Language).
    if "preferred_language" not in request.COOKIES:
        # Get the accept language,
        # Add the cookie to render.
        accept_language = request.LANGUAGE_CODE[:2]  # only support 'en' not 'en-gb'
        response.set_cookie(key="preferred_language", value=accept_language)

    return response


def emptypage(request):
    return render(request, "map/empty.html")


def countries_and_layers():
    confs = Configuration.objects.all().filter(is_displayed=True).order_by("display_order")

    # returns this, translated according to the preferred locale, this should be JS in the future:
    countries = {
        "EN": {
            "name": "",
            "flag": "",
            "code": "EN",
            "layers": [],
        },
    }

    # use django countries to augment this infromation based on the current prefered language,
    # which unfortunately doesn't change when switching language, but ok... for now it's fine.
    countries = {}
    for conf in confs:
        if conf.country.code not in countries:
            countries = {
                **countries,
                **{
                    conf.country.code: {
                        "code": conf.country.code,
                        "name": conf.country.name,
                        "flag": conf.country.flag,
                        "layers": [conf.organization_type.name],
                    }
                },
            }
        else:
            countries[conf.country]["layers"].append(conf.organization_type.name)

    return countries


def config_content():
    # This is converted to some hierarchy to make more sense, and to _not_ export things like keys
    metadata = get_backend_scanmetadata()

    # To enable landing pages, reset the application(!)
    lps = {}
    landingpages = (
        LandingPage.objects.all()
        .filter(enabled=True)
        .prefetch_related("map_configuration", "map_configuration__organization_type")
    )
    for landingpage in landingpages:
        lps[landingpage.directory] = {
            "country": landingpage.map_configuration.country.code,
            "layer": landingpage.map_configuration.organization_type.name,
        }

    configuration = get_all_values()
    scan_types = get_scanners_for_frontend(configuration)
    base_config = {
        "show": {
            "intro": configuration["SHOW_INTRO"],
            "multi_map_summary_table": configuration["SHOW_MULTI_MAP_SUMMARY_TABLE"],
            "charts": configuration["SHOW_CHARTS"],
            "comply_or_explain": configuration["SHOW_COMPLY_OR_EXPLAIN"],
            "scan_schedule": configuration["SHOW_SCAN_SCHEDULE"],
            "datasets": configuration["SHOW_DATASETS"],
            "announcement": configuration["SHOW_ANNOUNCEMENT"],
            "statistics": configuration["SHOW_EXTENSIVE_STATISTICS"],
            "numbers": configuration["SHOW_STATS_NUMBERS"],
            "improvements": configuration["SHOW_STATS_IMPROVEMENTS"],
            "graphs": configuration["SHOW_STATS_GRAPHS"],
            "changes": configuration["SHOW_STATS_CHANGES"],
            "ticker": configuration["SHOW_TICKER"],
            "services": configuration["SHOW_SERVICES"],
            "services_table": configuration["SHOW_SERVICES_TABLE"],
            "plus_info": configuration["PLUS_SHOW_INFO"],
            "report_numbers": configuration["SHOW_REPORT_NUMBERS"],
            "report_charts": configuration["SHOW_REPORT_CHARTS"],
            "report_charts_network": configuration["SHOW_REPORT_CHARTS_NETWORK"],
            "report_risk_summary": configuration["SHOW_REPORT_RISK_SUMMARY"],
            "report_content": configuration["SHOW_REPORT_CONTENT"],
            "report_website_gallery": configuration["SHOW_REPORT_WEBSITE_GALLERY"],
            "disclaimer": configuration["SHOW_DISCLAIMER"],
            "send_in_new_domains": configuration["SHOW_SEND_IN_NEW_DOMAINS"],
            "incorrect_finding": configuration["SHOW_INCORRECT_FINDING"],
            "snow": configuration["SHOW_SNOW"],
            "login_plaza": configuration["SHOW_LOGIN_PLAZA"],
            "time_machine": configuration["SHOW_TIME_MACHINE"],
            "historic_comparison_reports": configuration["SHOW_HISTORIC_COMPARISON_REPORTS"],
            "metric_progress": configuration["SHOW_METRIC_PROGRESS"],
            "comply_or_explain_guidelines": configuration["SHOW_COMPLY_OR_EXPLAIN_GUIDELINES"],
            "geolocation_results": configuration["SHOW_GEOLOCATION_RESULTS"],
            "thank_you": configuration["SHOW_THANK_YOU"],
            "socials": {
                "report": configuration["SOCIALS_SHOW_REPORT"],
                "map": configuration["SOCIALS_SHOW_MAP"],
                "charts": configuration["SOCIALS_SHOW_CHARTS"],
                "statistics": configuration["SOCIALS_SHOW_STATISTICS"],
                "multi_map": configuration["SOCIALS_SHOW_MULTI_MAP"],
            },
            "issues": {},
        },
        "announcement": configuration["ANNOUNCEMENT"],
        "disclaimer": configuration["DISCLAIMER_HTML"],
        "responsible_organization": {
            "name": configuration["RESPONSIBLE_ORGANIZATION_NAME"],
            "promo_text": configuration["RESPONSIBLE_ORGANIZATION_PROMO_TEXT"],
            "website": configuration["RESPONSIBLE_ORGANIZATION_WEBSITE"],
            "mail": configuration["RESPONSIBLE_ORGANIZATION_MAIL"],
            "twitter": configuration["RESPONSIBLE_ORGANIZATION_TWITTER"],
            "facebook": configuration["RESPONSIBLE_ORGANIZATION_FACEBOOK"],
            "linkedin": configuration["RESPONSIBLE_ORGANIZATION_LINKEDIN"],
            "whatsapp": configuration["RESPONSIBLE_ORGANIZATION_WHATSAPP"],
            "phone": configuration["RESPONSIBLE_ORGANIZATION_PHONE"],
        },
        "project": {
            "name": configuration["PROJECT_NAME"],
            "tagline": configuration["PROJECT_TAGLINE"],
            "country": configuration["PROJECT_COUNTRY"],
            "mail": configuration["PROJECT_MAIL"],
            "issue_mail": configuration["PROJECT_ISSUE_MAIL"],
            "twitter": configuration["PROJECT_TWITTER"],
            "facebook": configuration["PROJECT_FACEBOOK"],
        },
        "responsible_disclosure_page": {
            "show": configuration["SHOW_RESPONSIBLE_DISCLOSURE_POLICY"],
            "email_address": configuration["RESPONSIBLE_DISCLOSURE_EMAIL_ADDRESS"],
            "pgp_key": configuration["RESPONSIBLE_DISCLOSURE_PGP_KEY"],
            "salsa_key": configuration["RESPONSIBLE_DISCLOSURE_SALSA_KEY"],
        },
        "translations": {
            "en": {
                "landing": {
                    "title": configuration["INTRO_TITLE_HTML_EN"],
                    "leader": configuration["INTRO_LEADER_HTML_EN"],
                    "side_wide_search": configuration["SIDE_WIDE_SEARCH_TITLE_EN"],
                },
                "info": {
                    "title": configuration["INFO_TITLE_EN"],
                    "heading": configuration["INFO_HEADING_EN"],
                    "title_1": configuration["INFO_TITLE_1_EN"],
                    "content_1": configuration["INFO_CONTENT_1_EN"],
                    "title_2": configuration["INFO_TITLE_2_EN"],
                    "content_2": configuration["INFO_CONTENT_2_EN"],
                    "title_3": configuration["INFO_TITLE_3_EN"],
                    "content_3": configuration["INFO_CONTENT_3_EN"],
                    "title_4": configuration["INFO_TITLE_4_EN"],
                    "content_4": configuration["INFO_CONTENT_4_EN"],
                    "title_5": configuration["INFO_TITLE_5_EN"],
                    "content_5": configuration["INFO_CONTENT_5_EN"],
                },
                "footer": {
                    "content": configuration["FOOTER_CONTENT_HTML_EN"],
                },
                "thank_you_email": {
                    "will_fix_subject": configuration["THANK_YOU_WILL_FIX_EMAIL_SUBJECT_EN"],
                    "will_fix_body": configuration["THANK_YOU_WILL_FIX_EMAIL_BODY_EN"],
                    "thank_you_subject": configuration["THANK_YOU_EMAIL_SUBJECT_EN"],
                    "thank_you_body": configuration["THANK_YOU_EMAIL_BODY_EN"],
                },
            },
            "nl": {
                "landing": {
                    "title": configuration["INTRO_TITLE_HTML_NL"],
                    "leader": configuration["INTRO_LEADER_HTML_NL"],
                    "side_wide_search": configuration["SIDE_WIDE_SEARCH_TITLE_NL"],
                },
                "info": {
                    "title": configuration["INFO_TITLE_NL"],
                    "heading": configuration["INFO_HEADING_NL"],
                    "title_1": configuration["INFO_TITLE_1_NL"],
                    "content_1": configuration["INFO_CONTENT_1_NL"],
                    "title_2": configuration["INFO_TITLE_2_NL"],
                    "content_2": configuration["INFO_CONTENT_2_NL"],
                    "title_3": configuration["INFO_TITLE_3_NL"],
                    "content_3": configuration["INFO_CONTENT_3_NL"],
                    "title_4": configuration["INFO_TITLE_4_NL"],
                    "content_4": configuration["INFO_CONTENT_4_NL"],
                    "title_5": configuration["INFO_TITLE_5_NL"],
                    "content_5": configuration["INFO_CONTENT_5_NL"],
                },
                "footer": {
                    "content": configuration["FOOTER_CONTENT_HTML_NL"],
                },
                "thank_you_email": {
                    "will_fix_subject": configuration["THANK_YOU_WILL_FIX_EMAIL_SUBJECT_NL"],
                    "will_fix_body": configuration["THANK_YOU_WILL_FIX_EMAIL_BODY_NL"],
                    "thank_you_subject": configuration["THANK_YOU_EMAIL_SUBJECT_NL"],
                    "thank_you_body": configuration["THANK_YOU_EMAIL_BODY_NL"],
                },
            },
        },
        "comply_or_explain": {
            "forum_link": configuration["COMPLY_OR_EXPLAIN_DISCUSSION_FORUM_LINK"],
            "email_address": configuration["COMPLY_OR_EXPLAIN_EMAIL_ADDRESS"],
            "email_subject": configuration["COMPLY_OR_EXPLAIN_EMAIL_SUBJECT"],
            "email_body": configuration["COMPLY_OR_EXPLAIN_EMAIL_BODY"],
        },
        "send_in_new_domains": {
            "email_address": configuration["NEW_DOMAINS_EMAIL_ADDRESS"],
            "email_subject": configuration["NEW_DOMAINS_EMAIL_SUBJECT"],
            "email_body": configuration["NEW_DOMAINS_EMAIL_BODY"],
        },
        "incorrect_finding": {
            "email_address": configuration["INCORRECT_FINDING_EMAIL_ADDRESS"],
            "email_subject": configuration["INCORRECT_FINDING_EMAIL_SUBJECT"],
            "email_body": configuration["INCORRECT_FINDING_EMAIL_BODY"],
        },
        "debug": bool(settings.DEBUG),
        "admin": settings.ADMIN,
        "country_and_layers": countries_and_layers(),
        "google_maps_api_key": configuration["GOOGLE_MAPS_API_KEY"],
        "grading_policy": configuration["GRADING_POLICY"],
        "app": {
            "menu": configuration["MENU"],
            "custom_css": configuration["CUSTOM_CSS"],
            "logo_image": configuration["LOGO_IMAGE"],
            "favicon": configuration["FAVICON"],
            "thank_you_email_address": configuration["THANK_YOU_EMAIL_ADDRESS"],
            "relevant_for_ui": {
                "high": configuration["RELEVANT_FOR_UI_HIGH"],
                "medium": configuration["RELEVANT_FOR_UI_MEDIUM"],
                "low": configuration["RELEVANT_FOR_UI_LOW"],
                "good": configuration["RELEVANT_FOR_UI_GOOD"],
            },
            "landing_pages": lps,
        },
        "scan_types": scan_types,
    }

    # todo: only include the issues that are published, not everything that exists.
    for scan_type in sorted(metadata["published_scan_types"]):
        base_config["show"]["issues"][scan_type.lower()] = True

    return base_config


@cache_page(TEN_MINUTES)
def config(request) -> HttpResponse:
    # return JsonResponse(config_content(), encoder=orjson.dumps)
    return HttpResponse(orjson.dumps(config_content()), content_type="text/json", status=200)


@cache_page(TEN_MINUTES)
def index(request, map_configuration=None):
    initial_countries = get_initial_countries()

    if map_configuration:
        map_defaults = {"country": map_configuration.country, "layer": map_configuration.organization_type.name}
    else:
        map_defaults = get_defaults()

    # instead of asking for every config variable, get all of them in one go
    my_config = get_bulk_values(
        [
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
            "SHOW_SERVICES_TABLE",
            "SHOW_FTP",
            "SHOW_PLAIN_HTTP",
            "SHOW_DNSSEC",
            "PLUS_SHOW_INFO",
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
        ]
    )

    # a number of variables are injected so they can be used inside javascript.
    return inject_default_language_cookie(
        request,
        render(
            request,
            "map/index.html",
            {
                "configuration": my_config,
                "version": __version__,
                "admin": settings.ADMIN,
                "sentry_token": settings.SENTRY_TOKEN,
                "country": my_config["PROJECT_COUNTRY"],
                "debug": bool(settings.DEBUG),
                "language": request.LANGUAGE_CODE[0:2],  # only support 'en' not 'en-gb',
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "initial_map_data_url": "",
                "initial_countries": initial_countries,
                "countries_and_layers": countries_and_layers(),
                "default_country": map_defaults["country"],
                "default_layer": map_defaults["layer"],
                "default_week": 0,
                "number_of_countries": len(initial_countries),
                "initial_map_data": get_map_data(map_defaults["country"], map_defaults["layer"], 0, ""),
            },
        ),
    )


@cache_page(TEN_MINUTES)
def robots_txt(request):
    return render(request, "map/robots.txt", content_type="text/plain")


@cache_page(TEN_MINUTES)
def security_txt(request):
    config = get_bulk_values(["SECURITY_TXT_IS_REDIRECTED", "SECURITY_TXT_REDIRECT_URL", "SECURITY_TXT_CONTENT"])

    if config["SECURITY_TXT_IS_REDIRECTED"]:
        return HttpResponseRedirect(config["SECURITY_TXT_REDIRECT_URL"])

    # constance trims data stored in the database, the standard says it needs to end in CRLF.
    return HttpResponse(config["SECURITY_TXT_CONTENT"] + "\r\n", content_type="text/plain")


@cache_page(TEN_MINUTES)
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
            {"src": "static/favicons/android-icon-36x36.png", "sizes": "36x36", "type": "image/png", "density": "0.75"},
            {"src": "static/favicons/android-icon-48x48.png", "sizes": "48x48", "type": "image/png", "density": "1.0"},
            {"src": "static/favicons/android-icon-72x72.png", "sizes": "72x72", "type": "image/png", "density": "1.5"},
            {"src": "static/favicons/android-icon-96x96.png", "sizes": "96x96", "type": "image/png", "density": "2.0"},
            {
                "src": "static/favicons/android-icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "density": "3.0",
            },
            {
                "src": "static/favicons/android-icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "density": "4.0",
            },
        ],
    }
    return JsonResponse(manifest, encoder=JSEncoder)


@cache_page(TEN_MINUTES)
def organization_report_by_id(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
    organization_id=None,
    days_back=0,
    at_date: date = None,
):
    return json_response(get_organization_report_by_id(organization_id, days_back, at_date=at_date))


@cache_page(TEN_MINUTES)
def organization_report_by_name(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
    organization_name=None,
    days_back=0,
    at_date: date = None,
):
    if not (organization_name and country and organization_type):
        return empty_response()

    return json_response(
        get_organization_report_by_name(
            organization_name=organization_name,
            country=country,
            organization_type=organization_type,
            days_back=days_back,
            at_date=at_date,
        )
    )


@cache_page(TEN_MINUTES)
def top_fail(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, days_back=0, at_date: date = None
):
    return json_response(get_top_fail_data(country, organization_type, days_back, at_date=at_date))


@cache_page(TEN_MINUTES)
def top_win(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, days_back=0, at_date: date = None
):
    return json_response(get_top_win_data(country, organization_type, days_back, at_date=at_date))


@cache_page(TEN_MINUTES)
def stats(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type=DEFAULT_LAYER,
    days_back=0,
    duration: int = 365,
    at_date: date = None,
):
    return json_response(get_stats(country, organization_type, days_back, duration, at_date=at_date))


@cache_page(TEN_MINUTES)
def v_what_to_improve(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, issue_type=""):
    return json_response(what_to_improve(country, organization_type, issue_type))


@cache_page(TEN_MINUTES)
def get_short_and_simple_stats_(request, days_back=0, at_date: date = None):
    return json_response(get_short_and_simple_stats(days_back, at_date=at_date))


@cache_page(TEN_MINUTES)
def organization_vulnerability_timeline(request, organization_id: int, duration: int = 365):
    return json_response(get_organization_vulnerability_timeline(organization_id, duration=duration))


@cache_page(TEN_MINUTES)
def organization_vulnerability_timeline_via_name(
    request, organization_name: str, organization_type: str = "", country: str = "", duration: int = 365
):
    return json_response(
        get_organization_vulnerability_timeline_via_name(organization_name, organization_type, country, duration)
    )


@cache_page(TEN_MINUTES)
def vulnerability_graphs(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type=DEFAULT_LAYER,
    days_back=0,
    duration: int = 365,
    at_date: date = None,
):
    return json_response(get_vulnerability_graph(country, organization_type, days_back, duration, at_date=at_date))


@cache_page(TEN_MINUTES)
def improvements(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
    days_back: int = 0,
    duration: int = 0,
    at_date: date = None,
):
    return json_response(get_improvements(country, organization_type, days_back, duration, at_date=at_date))


@cache_page(TEN_MINUTES)
def ticker(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
    days_back: int = 0,
    duration: int = 0,
    at_date: date = None,
):
    return json_response(get_ticker_data(country, organization_type, days_back, duration, at_date=at_date))


@cache_page(TEN_MINUTES)
def map_default(request, days_back: int = 0, displayed_issue: str = "all", at_date: date = None):
    my_defaults = (
        Configuration.objects.all()
        .filter(is_displayed=True, is_the_default_option=True)
        .order_by("display_order")
        .values("country", "organization_type__name")
        .first()
    )

    # On an empty database, just get the Netherlands.
    if not my_defaults:
        return map_data(request, DEFAULT_COUNTRY, DEFAULT_LAYER, days_back, displayed_issue, at_date=at_date)

    return map_data(
        request,
        my_defaults["country"],
        my_defaults["organization_type__name"],
        days_back,
        displayed_issue,
        at_date=at_date,
    )


@cache_page(TEN_MINUTES)
def organization_list(request, country: str = DEFAULT_COUNTRY, organization_type: str = DEFAULT_LAYER):
    query = (
        Organization.objects.all()
        .filter(country=get_country(country), layers=get_organization_type(organization_type), is_dead=False)
        .only("id", "name", "computed_name_slug")
    )

    data = []
    for record in query:
        # Get the latest organization report, if any, so to have some impression what the result will be when selecting
        # the organization:

        report = (
            OrganizationReport.objects.all()
            .filter(organization=record.id)
            .only("total_urls", "total_endpoints", "high", "medium", "low", "ok", "at_when")
            .last()
        )
        if report:
            data.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "slug": record.computed_name_slug,
                    "report_available": True,
                    "urls": report.total_urls,
                    "endpoints": report.total_endpoints,
                    "high": report.high,
                    "medium": report.medium,
                    "low": report.low,
                    "ok": report.ok,
                    "at_when": report.at_when,
                }
            )
        else:
            data.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "slug": record.computed_name_slug,
                    "report_available": False,
                    "urls": 0,
                    "endpoints": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "ok": 0,
                    "at_when": None,
                }
            )

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@cache_page(TEN_MINUTES)
def map_data(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
    days_back: int = 0,
    displayed_issue: str = "all",
    at_date: date = None,
):
    data = get_map_data(country, organization_type, days_back, displayed_issue, at_date=at_date)

    return HttpResponse(orjson.dumps(data), content_type="text/json", status=200)


@cache_page(TEN_MINUTES)
def all_latest_scans(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER):
    return json_response(get_all_latest_scans(country, organization_type))


@cache_page(TEN_MINUTES)
def explain_list(request, country, organization_type):
    return json_response(get_recent_explains(country, organization_type))


@cache_page(TEN_MINUTES)
def updates_on_organization(request, organization_id):
    return json_response(latest_updates(organization_id))


def organization_autcomplete(
    request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, parameter: str = ""
):
    # See Django Auto Complete for more info.
    qs = Organization.objects.all()
    qs = qs.filter(type=get_organization_type(organization_type))
    qs = qs.filter(country=get_country(country))
    qs = qs.filter(name__icontains=parameter).values_list("name", flat=True)

    return JsonResponse(list(qs), encoder=JSEncoder, safe=False)


@cache_page(TEN_MINUTES)
def upcoming_and_past_scans(request):
    return json_response(get_next_and_last_scans())


@cache_page(TEN_MINUTES)
def screenshot(request, endpoint_id=0):
    # get the latest screenshot from an endpoint.

    scrsht = Screenshot.objects.all().filter(endpoint=endpoint_id).order_by("-created_on").first()

    if not scrsht:
        return HttpResponse()

    if not scrsht.image:
        return HttpResponse()

    wrapper = FileWrapper(scrsht.image.file.open("rb"))
    return HttpResponse(wrapper, content_type="image/PNG")


def get_json_body(request):
    try:
        user_input = json.loads(request.body)
    except json.JSONDecodeError:
        user_input = {}

    return user_input


def v_explain(request):
    if not request.user.is_authenticated:
        return JsonResponse({}, encoder=JSEncoder, safe=False)

    request = get_json_body(request)

    data = explain(
        request.get("scan_id"),
        request.get("scan_type"),
        request.get("explanation"),
        request.get("explained_by"),
        request.get("validity"),
    )

    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def v_remove_explain(request):
    request = get_json_body(request)
    return json_response(remove_explanation(request.get("scan_id"), request.get("scan_type")))


@user_passes_test(user_is_staff_member)
def v_add_urls(request):
    request = get_json_body(request)
    return json_response(add_urls(request.get("organization_id"), request.get("urls")))


@user_passes_test(user_is_staff_member)
def v_add_proxies(request):
    request = get_json_body(request)
    data = add_proxies(request.get("proxies"))
    return JsonResponse(data, encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def v_switch_lattitude_and_longitude(request, organization_id=0):
    return JsonResponse(switch_lattitude_and_longitude(organization_id), encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def v_add_organization(request):
    request = get_json_body(request)
    return JsonResponse(add_organization(request), encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def v_move_coordinate(request):
    request = get_json_body(request)
    return JsonResponse(move_coordinate(request), encoder=JSEncoder, safe=False)


@user_passes_test(user_is_staff_member)
def v_delete_coordinate(request):
    request = get_json_body(request)
    return JsonResponse(delete_coordinate(request), encoder=JSEncoder, safe=False)


def planned_scan_progress(request):
    return JsonResponse(plannedscan.get_latest_progress(), encoder=JSEncoder, safe=False)


def map_health(request, country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER):
    return JsonResponse(get_lastest_map_health_data(country, organization_type), encoder=JSEncoder, safe=False)


@cache_page(ONE_HOUR)
def login_plaza(
    request,
    country: str = DEFAULT_COUNTRY,
    organization_type: str = DEFAULT_LAYER,
):
    if not (country and organization_type):
        return JsonResponse([], encoder=JSEncoder, safe=False)

    if not constance_cached_value("SHOW_LOGIN_PLAZA"):
        return JsonResponse([], encoder=JSEncoder, safe=False)

    return json_response(
        login_plaza_data(
            country=country,
            layer=organization_type,
        )
    )


@cache_page(ONE_HOUR)
def login_plaza_products(request):
    return json_response(get_products())
