# urls for scanners, maybe in their own url files
import proxy.views
from django.conf import settings
from django.conf.urls import url
from django.urls import path, register_converter
from django.views.i18n import JavaScriptCatalog

from . import views
from .. import converters

# todo: organization type converter doesn't work yet... using slug as an alternative.
register_converter(converters.OrganizationTypeConverter, 'ot')
register_converter(converters.WeeksConverter, 'w')
register_converter(converters.CountryConverter, 'c')
register_converter(converters.OrganizationIdConverter, 'oid')

urlpatterns = [
    path('', views.index),
    path('security.txt', views.security_txt),
    path('robots.txt', views.robots_txt),
    path('manifest.json', views.manifest_json),

    path('data/organizationtype_exists/<slug:organization_type_name>', views.organizationtype_exists),
    path('data/map/<c:country>/<slug:organization_type>/<w:weeks_back>', views.map_data),
    path('data/stats/<c:country>/<slug:organization_type>/<w:weeks_back>', views.stats),
    path('data/countries/', views.get_countries),
    path('data/default_country/', views.get_default_country),
    path('data/default_category/', views.get_default_category),
    path('data/default_category_for_country/<c:country>/', views.get_default_category_for_country),
    path('data/categories/<c:country>/', views.get_categories),
    path('data/vulnstats/<c:country>/<slug:organization_type>/<w:weeks_back>', views.vulnerability_graphs),
    path('data/topfail/<c:country>/<slug:organization_type>/<w:weeks_back>', views.top_fail),
    path('data/topwin/<c:country>/<slug:organization_type>/<w:weeks_back>', views.top_win),

    path('data/latest_scans/<c:country>/<slug:organization_type>/<slug:scan_type>', views.latest_scans),
    path('data/feed/<slug:scan_type>', views.LatestScanFeed()),
    path('data/terrible_urls/<c:country>/<slug:organization_type>/<w:weeks_back>', views.terrible_urls,),
    path('data/improvements/<c:country>/<slug:organization_type>/<w:weeks_back>/<w:weeks_duration>',
         views.improvements),
    path('data/ticker/<c:country>/<slug:organization_type>/<w:weeks_back>/<w:weeks_duration>', views.ticker),
    path('data/wanted/', views.wanted_urls),
    path('data/report/<oid:organization_id>/<w:weeks_back>', views.organization_report),
    path('data/report/<str:organization_name>/<w:weeks_back>', views.organization_report),
    path('data/updates_on_organization/<oid:organization_id>', views.updates_on_organization),
    path('data/updates_on_organization_feed/<oid:organization_id>', views.UpdatesOnOrganizationFeed()),

    path('data/export/urls_only/<c:country>/<slug:organization_type>/', views.export_urls_only),
    path('data/export/organization_types/<c:country>/<slug:organization_type>/', views.export_organization_types),
    path('data/export/organizations/<c:country>/<slug:organization_type>/', views.export_organizations),
    path('data/export/coordinates/<c:country>/<slug:organization_type>/', views.export_coordinates),
    path('data/export/urls/<c:country>/<slug:organization_type>/', views.export_urls),

    # Proxy maptile requests,
    # In production this can be done by caching proxy, this makes sure it works for dev. as well.
    url(r'^proxy/(?P<url>https://api.tiles.mapbox.com/v4/.*.png$)',
        proxy.views.proxy_view,
        {"requests_args": {"params": {"access_token": settings.MAPBOX_TOKEN}}}),

    # translations for javascript files. Copied from the manual.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/
    # cache_page(86400, key_prefix='js18n')
    url(r'^jsi18n/map/$', JavaScriptCatalog.as_view(packages=['failmap.map']), name='javascript-catalog'),
]
