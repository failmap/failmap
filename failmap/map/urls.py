# urls for scanners, maybe in their own url files
import proxy.views
from django.conf import settings
from django.conf.urls import url
from django.views.i18n import JavaScriptCatalog

from failmap.map.views import (LatestScanFeed, UpdatesOnOrganizationFeed, export_urls_only, export_full_dataset,
export_urls_and_organizations,
                               get_categories, get_countries, get_default_category,
                               get_default_country, improvements, index, latest_scans,
                               manifest_json, map_data, organization_report,
                               organizationtype_exists, robots_txt, security_txt, stats,
                               terrible_urls, ticker, top_fail, top_win, updates_on_organization,
                               vulnerability_graphs, wanted_urls)

urlpatterns = [
    url(r'^$', index, name='failmap'),
    url(r'^security.txt$', security_txt),
    url(r'^robots.txt$', robots_txt),
    url(r'^manifest.json$', manifest_json),
    url(r'^data/organizationtype_exists/(?P<organization_type_name>[a-z_\-]{0,50})',
        organizationtype_exists, name='set category'),

    url(r'^data/map/(?P<country>[A-Z]{2})/(?P<organization_type>[0-9A-Za-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        map_data, name='map data'),

    url(r'^data/stats/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        stats, name='stats'),

    url(r'^data/countries/',
        get_countries, name='get_countries'),

    url(r'^data/default_country/',
        get_default_country, name='default_country'),

    url(r'^data/default_category/',
        get_default_category, name='default_category'),

    url(r'^data/categories/(?P<country>[A-Z]{2})/',
        get_categories, name='get_categories'),

    url(r'^data/vulnstats/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        vulnerability_graphs, name='vulnstats'),

    url(r'^export/url/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/',
        export_urls_only, name='url export'),

    url(r'^export/organizations/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/',
        export_urls_and_organizations, name='url export'),

    url(r'^export/full/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/',
        export_full_dataset, name='url export'),

    url(r'^data/topfail/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        top_fail, name='top fail'),
    url(r'^data/topwin/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        top_win, name='top win'),
    url(r'^data/latest_scans/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/'
        r'(?P<scan_type>[a-zA-Z_-]{0,100})',
        latest_scans, name='latest scans'),
    url(r'^data/feed/(?P<scan_type>[a-zA-Z_-]{0,100})$', LatestScanFeed()),
    # disabled until the url ratings are improved to reflect dead endpoints and such too(!)
    url(r'^data/terrible_urls/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/(?P<weeks_back>[0-9]{0,2})',
        terrible_urls, name='terrible urls'),
    url(r'^data/improvements/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/'
        r'(?P<weeks_back>[0-9]{0,2})/(?P<weeks_duration>[0-9]{0,2})',
        improvements, name='improvements'),
    url(r'^data/ticker/(?P<country>[A-Z]{2})/(?P<organization_type>[a-z_\-]{0,50})/'
        r'(?P<weeks_back>[0-9]{0,2})/(?P<weeks_duration>[0-9]{0,2})',
        ticker, name='ticker'),
    url(r'^data/wanted/', wanted_urls, name='wanted urls'),
    url(r'^data/report/(?P<organization_id>[0-9]{0,200})/(?P<weeks_back>[0-9]{0,2})$',
        organization_report, name='organization report'),
    url(r'^data/report/(?P<organization_name>[a-z-]{0,200})/(?P<weeks_back>[0-9]{0,2})$',
        organization_report, name='organization report'),

    url(r'^data/updates_on_organization/(?P<organization_id>[0-9]{1,6})$', updates_on_organization, name='asdf'),
    url(r'^data/updates_on_organization_feed/(?P<organization_id>[0-9]{1,6})$', UpdatesOnOrganizationFeed()),
    # proxy maptile requests, in production this can be done by caching proxy, this makes sure
    # it works for dev. as well.
    url(r'^proxy/(?P<url>https://api.tiles.mapbox.com/v4/.*.png$)',
        proxy.views.proxy_view,
        {"requests_args": {"params": {"access_token": settings.MAPBOX_TOKEN}}}),

    # translations for javascript files. Copied from the manual.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/
    # cache_page(86400, key_prefix='js18n')
    url(r'^jsi18n/map/$', JavaScriptCatalog.as_view(packages=['failmap.map']), name='javascript-catalog'),
]
