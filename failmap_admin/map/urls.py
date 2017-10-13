# urls for scanners, maybe in their own url files
from django.conf.urls import url

from failmap_admin.map.views import (index, map_data, organization_report, stats, terrible_urls,
                                     topfail, topwin, wanted_urls, robots_txt, security_txt)

urlpatterns = [
    url(r'^security.txt$', security_txt),
    url(r'^robots.txt$', robots_txt),
    url(r'^data/map/(?P<weeks_back>[0-9]{0,2})', map_data, name='map data'),
    url(r'^data/stats/(?P<weeks_back>[0-9]{0,2})', stats, name='stats'),
    url(r'^data/topfail/(?P<weeks_back>[0-9]{0,2})', topfail, name='top fail'),
    url(r'^data/topwin/(?P<weeks_back>[0-9]{0,2})', topwin, name='top win'),
    # disabled until the url ratings are improved to reflect dead endpoints and such too(!)
    url(r'^data/terrible_urls/(?P<weeks_back>[0-9]{0,2})', terrible_urls, name='terrible urls'),
    url(r'^data/wanted/', wanted_urls, name='wanted urls'),
    url(r'^data/report/(?P<organization_id>[0-9]{0,200})/(?P<weeks_back>[0-9]{0,2})$',
        organization_report, name='organization report'),
    url(r'^$', index, name='failmap'),
]
