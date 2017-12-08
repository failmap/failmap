# urls for scanners, maybe in their own url files
import proxy.views
from django.conf import settings
from django.conf.urls import url

from failmap_admin.map.views import (LatestScanFeed, index, latest_scans, manifest_json, map_data,
                                     organization_report, robots_txt, security_txt, stats,
                                     terrible_urls, topfail, topwin, vulnstats, wanted_urls)

urlpatterns = [
    url(r'^security.txt$', security_txt),
    url(r'^robots.txt$', robots_txt),
    url(r'^manifest.json$', manifest_json),
    url(r'^data/map/(?P<weeks_back>[0-9]{0,2})', map_data, name='map data'),
    url(r'^data/stats/(?P<weeks_back>[0-9]{0,2})', stats, name='stats'),

    # url(r'^d3.html', d3, name='d3'),
    url(r'^data/vulnstats/(?P<weeks_back>[0-9]{0,2})', vulnstats, name='vulnstats'),
    url(r'^data/topfail/(?P<weeks_back>[0-9]{0,2})', topfail, name='top fail'),
    url(r'^data/topwin/(?P<weeks_back>[0-9]{0,2})', topwin, name='top win'),
    url(r'^data/latest_scans/(?P<scan_type>[a-zA-Z_-]{0,100})', latest_scans, name='latest scans'),
    url(r'^data/feed/(?P<scan_type>[a-zA-Z_-]{0,100})$', LatestScanFeed()),
    # disabled until the url ratings are improved to reflect dead endpoints and such too(!)
    url(r'^data/terrible_urls/(?P<weeks_back>[0-9]{0,2})', terrible_urls, name='terrible urls'),
    url(r'^data/wanted/', wanted_urls, name='wanted urls'),
    url(r'^data/report/(?P<organization_id>[0-9]{0,200})/(?P<weeks_back>[0-9]{0,2})$',
        organization_report, name='organization report'),
    url(r'^$', index, name='failmap'),
    # proxy maptile requests, in production this can be done by caching proxy, this makes sure
    # it works for dev. as well.
    url(r'^proxy/(?P<url>https://api.tiles.mapbox.com/v4/.*.png$)',
        proxy.views.proxy_view,
        {"requests_args": {"params": {"access_token": settings.MAPBOX_TOKEN}}})
]
