# urls for scanners, maybe in their own url files
import proxy.views
from constance import config
from django.db import connection
from django.urls import path, register_converter
from django.views.i18n import JavaScriptCatalog
from django.urls import re_path

import websecmap.map.logic.rss_feeds
from websecmap import converters
from websecmap.map import views

# todo: organization type converter doesn't work yet... using slug as an alternative.
from websecmap.map.models import LandingPage

register_converter(converters.OrganizationTypeConverter, "ot")
register_converter(converters.WeeksConverter, "w")
register_converter(converters.DaysConverter, "d")
register_converter(converters.CountryConverter, "c")
register_converter(converters.OrganizationIdConverter, "oid")
register_converter(converters.JsonConverter, "json")

static_urlpatterns = [
    path("", views.index),
    path("data/config/", views.config),
    path("empty", views.emptypage),
    path("security.txt", views.security_txt),
    path("robots.txt", views.robots_txt),
    path("manifest.json", views.manifest_json),
    path(
        "autocomplete/<c:country>/<slug:organization_type>/organization/<str:parameter>", views.organization_autcomplete
    ),
    path("data/map/<c:country>/<slug:organization_type>/<d:days_back>/<slug:displayed_issue>/", views.map_data),
    path("data/map/<c:country>/<slug:organization_type>/<d:days_back>//", views.map_data),
    path("data/organizations/list/<c:country>/<slug:organization_type>/", views.organization_list),
    path("data/map_default/<d:days_back>/<slug:displayed_issue>/", views.map_default),
    path("data/map_default/<d:days_back>//", views.map_default),
    path("data/stats/<c:country>/<slug:organization_type>/<w:weeks_back>", views.stats),
    path("data/short_and_simple_stats/<w:weeks_back>/", views.get_short_and_simple_stats_),
    # defaults
    path("data/defaults/", views.defaults),
    path("data/layers/<c:country>/", views.layers),
    path("data/vulnerability_graphs/<c:country>/<slug:organization_type>/<w:weeks_back>", views.vulnerability_graphs),
    path("data/topfail/<c:country>/<slug:organization_type>/<w:weeks_back>", views.top_fail),
    path("data/topwin/<c:country>/<slug:organization_type>/<w:weeks_back>", views.top_win),
    path("data/all_latest_scans/<c:country>/<slug:organization_type>/", views.all_latest_scans),
    path("data/feed/<slug:scan_type>", websecmap.map.logic.rss_feeds.LatestScanFeed()),
    path(
        "data/improvements/<c:country>/<slug:organization_type>/<w:weeks_back>/<w:weeks_duration>", views.improvements
    ),
    path("data/ticker/<c:country>/<slug:organization_type>/<w:weeks_back>/<w:weeks_duration>", views.ticker),
    path("data/explained/<c:country>/<slug:organization_type>/", views.explain_list),
    # be compatible with optional parameters and types.
    path("data/organization_vulnerability_timeline/<oid:organization_id>", views.organization_vulnerability_timeline),
    path(
        "data/organization_vulnerability_timeline/<oid:organization_id>/<slug:organization_type>/<c:country>",
        views.organization_vulnerability_timeline,
    ),
    path(
        "data/organization_vulnerability_timeline/<str:organization_name>/<slug:organization_type>/<c:country>",
        views.organization_vulnerability_timeline_via_name,
    ),
    path(
        "data/organization_vulnerability_timeline/<str:organization_name>/",
        views.organization_vulnerability_timeline_via_name,
    ),
    path(
        "data/report/<c:country>/<slug:organization_type>/<oid:organization_id>/<w:weeks_back>",
        views.organization_report_by_id,
    ),
    path(
        "data/report/<c:country>/<slug:organization_type>/<str:organization_name>/<w:weeks_back>",
        views.organization_report_by_name,
    ),
    path("data/updates_on_organization/<oid:organization_id>", views.updates_on_organization),
    path(
        "data/updates_on_organization_feed/<oid:organization_id>",
        websecmap.map.logic.rss_feeds.UpdatesOnOrganizationFeed(),
    ),
    # dataset downloads
    path("data/export/urls_only/<c:country>/<slug:organization_type>/<slug:file_format>/", views.export_urls_only),
    path(
        "data/export/organization_types/<c:country>/<slug:organization_type>/<slug:file_format>/",
        views.export_organization_types,
    ),
    path(
        "data/export/organizations/<c:country>/<slug:organization_type>/<slug:file_format>/", views.export_organizations
    ),
    path("data/export/coordinates/<c:country>/<slug:organization_type>/<slug:file_format>/", views.export_coordinates),
    path("data/export/urls/<c:country>/<slug:organization_type>/<slug:file_format>/", views.export_urls),
    # this is not a single dataset, so building all kinds of exports was a bit harder, when needed we can build it.
    path("data/export/explains/<c:country>/<slug:organization_type>/<slug:file_format>/", views.export_explains),
    path("data/upcoming_and_past_scans/", views.upcoming_and_past_scans),
    path("images/screenshot/<int:endpoint_id>/", views.screenshot),
    # Proxy maptile requests,
    # In production this can be done by caching proxy, this makes sure it works for dev. as well.
    re_path(
        r"^proxy/(?P<url>https://api.mapbox.com/styles/v1/mapbox/.*./$)",
        proxy.views.proxy_view,
        {"requests_args": {"params": {"access_token": config.MAPBOX_ACCESS_TOKEN}}},
    ),
    # Below functions only work in a live environment. You cannot post anything on the public version of this
    # software. It will only work on authenticated domains.
    path("data/explain/explain/", views._explain),
    path("data/explain/remove/", views._remove_explain),
    path("data/admin/urls/add/", views._add_urls),
    path("data/admin/proxy/add/", views._add_proxies),
    path("data/admin/map/switch_lat_lng/<oid:organization_id>/", views._switch_lattitude_and_longitude),
    path("data/admin/organization/add/", views._add_organization),
    # a progress bar for running scans...
    path("data/planned_scan_progress/", views.planned_scan_progress),
    path("data/map_health/<c:country>/<slug:organization_type>/", views.map_health),
    # translations for javascript files. Copied from the manual.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/
    # cache_page(86400, key_prefix='js18n')
    re_path(r"^jsi18n/map/$", JavaScriptCatalog.as_view(packages=["websecmap.map"]), name="javascript-catalog"),
]

# See if we already have access to this database object. If not, then skip this: map_landingpage,
# otherwise it will block migrations etc... Perhaps there is a smarter way to do this that is not blocking...
dynamic_urlpatterns = []
if "map_landingpage" in connection.introspection.table_names():
    # To enable landing pages, reset the application(!)
    landingpages = LandingPage.objects.all().filter(enabled=True)
    for landingpage in landingpages:
        dynamic_urlpatterns.append(
            path(landingpage.directory, views.index, {"map_configuration": landingpage.map_configuration})
        )

urlpatterns = static_urlpatterns + dynamic_urlpatterns
