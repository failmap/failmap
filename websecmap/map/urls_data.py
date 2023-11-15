# urls for scanners, maybe in their own url files
from django.urls import path, register_converter

import websecmap.map.logic.rss_feeds
from websecmap import converters
from websecmap.map import views as v

register_converter(converters.OrganizationTypeConverter, "ot")
register_converter(converters.WeeksConverter, "w")
register_converter(converters.DaysConverter, "d")
register_converter(converters.CountryConverter, "c")
register_converter(converters.OrganizationIdConverter, "oid")
register_converter(converters.JsonConverter, "json")
register_converter(converters.DateConverter, "ymd")

ovt = "organization_vulnerability_timeline"
vg = "vulnerability_graphs"
ot = "organization_types"
uoo = "updates_on_organization"
lp = "login_plaza"

ovtvn = v.organization_vulnerability_timeline_via_name

org_report_by_id = v.organization_report_by_id
org_report_by_name = v.organization_report_by_name

# these urls are exposed at the /data endpoint
# All endpoints always end in a single slash for consistency and expandability
# duration is always an integer in days
urlpatterns = [
    path("config/", v.config),
    # legacy
    path("defaults/", v.defaults),
    path("layers/<c:country>/", v.layers),
    path("map_default/<d:days_back>/<slug:displayed_issue>/", v.map_default),
    path("map_default/<ymd:at_date>/<slug:displayed_issue>/", v.map_default),
    path("map_default/<d:days_back>/", v.map_default),
    path("map_default/<ymd:at_date>/", v.map_default),
    # map
    path("map/<c:country>/<slug:organization_type>/<d:days_back>/<slug:displayed_issue>/", v.map_data),
    path("map/<c:country>/<slug:organization_type>/<ymd:at_date>/<slug:displayed_issue>/", v.map_data),
    path("map/<c:country>/<slug:organization_type>/<d:days_back>/", v.map_data),
    path("map/<c:country>/<slug:organization_type>/<ymd:at_date>/", v.map_data),
    # top
    path("topfail/<c:country>/<slug:organization_type>/<w:days_back>/", v.top_fail),
    path("topfail/<c:country>/<slug:organization_type>/<ymd:at_date>/", v.top_fail),
    path("topwin/<c:country>/<slug:organization_type>/<w:days_back>/", v.top_win),
    path("topwin/<c:country>/<slug:organization_type>/<ymd:at_date>/", v.top_win),
    # stats
    path("stats/<c:country>/<slug:organization_type>/<w:days_back>", v.stats),
    path("stats/<c:country>/<slug:organization_type>/<ymd:at_date>", v.stats),
    path("stats/<c:country>/<slug:organization_type>/<w:days_back>/<int:duration>/", v.stats),
    path("stats/<c:country>/<slug:organization_type>/<ymd:at_date>/<int:duration>/", v.stats),
    path("stats/what_to_improve/<c:country>/<slug:organization_type>/<str:issue_type>/", v.v_what_to_improve),
    path("short_and_simple_stats/<w:days_back>/", v.get_short_and_simple_stats_),
    path("short_and_simple_stats/<ymd:at_date>/", v.get_short_and_simple_stats_),
    path(f"{lp}/<c:country>/<slug:organization_type>/", v.login_plaza),
    path("cookie_plaza/<c:country>/<slug:organization_type>/", v.cookie_plaza),
    path("cookie_plaza/", v.cookie_plaza),
    path(f"{lp}/products/", v.login_plaza_products),
    path("cookies/indicators/", v.cookie_indicators),
    path(f"{vg}/<c:country>/<slug:organization_type>/<w:days_back>/", v.vulnerability_graphs),
    path(f"{vg}/<c:country>/<slug:organization_type>/<ymd:at_date>/", v.vulnerability_graphs),
    path(f"{vg}/<c:country>/<slug:organization_type>/<w:days_back>/<int:duration>/", v.vulnerability_graphs),
    path(f"{vg}/<c:country>/<slug:organization_type>/<ymd:at_date>/<int:duration>/", v.vulnerability_graphs),
    path(f"{ovt}/<oid:organization_id>/", v.organization_vulnerability_timeline),
    path(f"{ovt}/<oid:organization_id>/<int:duration>/", v.organization_vulnerability_timeline),
    path(f"{ovt}/<str:organization_name>/<slug:organization_type>/<c:country>/", ovtvn),
    path(f"{ovt}/<str:organization_name>/<slug:organization_type>/<c:country>/<int:duration>/", ovtvn),
    path(f"{ovt}/<str:organization_name>/", v.organization_vulnerability_timeline_via_name),
    path(f"{ovt}/<str:organization_name>/<int:duration>/", v.organization_vulnerability_timeline_via_name),
    # report selection and data
    path("organizations/list/<c:country>/<slug:organization_type>/", v.organization_list),
    path("report/<c:country>/<slug:organization_type>/<oid:organization_id>/<w:days_back>/", org_report_by_id),
    path("report/<c:country>/<slug:organization_type>/<oid:organization_id>/<ymd:at_date>/", org_report_by_id),
    path("report/<c:country>/<slug:organization_type>/<str:organization_name>/<w:days_back>/", org_report_by_name),
    path("report/<c:country>/<slug:organization_type>/<str:organization_name>/<ymd:at_date>/", org_report_by_name),
    # updates
    path(f"{uoo}/<oid:organization_id>/", v.updates_on_organization),
    path(f"{uoo}_feed/<oid:organization_id>/", websecmap.map.logic.rss_feeds.UpdatesOnOrganizationFeed()),
    # other data pages
    path("feed/<slug:scan_type>", websecmap.map.logic.rss_feeds.LatestScanFeed()),
    path("improvements/<c:country>/<slug:organization_type>/<w:days_back>/<w:duration>/", v.improvements),
    path("improvements/<c:country>/<slug:organization_type>/<ymd:at_date>/<w:duration>/", v.improvements),
    path("ticker/<c:country>/<slug:organization_type>/<w:days_back>/<w:duration>/", v.ticker),
    path("ticker/<c:country>/<slug:organization_type>/<ymd:at_date>/<w:duration>/", v.ticker),
    path("explained/<c:country>/<slug:organization_type>/", v.explain_list),
    # dataset downloads
    path("export/urls_only/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_urls_only),
    path(f"export/{ot}/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_organization_types),
    path("export/organizations/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_organizations),
    path("export/coordinates/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_coordinates),
    path("export/urls/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_urls),
    path("export/explains/<c:country>/<slug:organization_type>/<slug:file_format>/", v.export_explains),
    # metadata for external users, to give some insight in what is going on
    path("upcoming_and_past_scans/", v.upcoming_and_past_scans),
    path("all_latest_scans/<c:country>/<slug:organization_type>/", v.all_latest_scans),
    path("planned_scan_progress/", v.planned_scan_progress),
    path("map_health/<c:country>/<slug:organization_type>/", v.map_health),
    # admin features
    # Below functions only work in a live environment. You cannot post anything on the public version of this
    # software. It will only work on authenticated domains.
    path("explain/explain/", v.v_explain),
    path("explain/remove/", v.v_remove_explain),
    path("admin/urls/add/", v.v_add_urls),
    path("admin/proxy/add/", v.v_add_proxies),
    path("admin/map/switch_lat_lng/<oid:organization_id>/", v.v_switch_lattitude_and_longitude),
    path("admin/organization/add/", v.v_add_organization),
    path("admin/organization/move_coordinate/", v.v_move_coordinate),
    path("admin/organization/delete_coordinate/", v.v_delete_coordinate),
]
