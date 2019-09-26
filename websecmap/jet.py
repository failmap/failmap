from django.utils.translation import gettext_lazy as _


def websecmap_menu_items():
    return [

        {'label': _('🗺️ Map'), 'items': [
            {'name': 'map.configuration', 'label': _('Map Configuration')},
            {'name': 'map.landingpage', 'label': _('Landing Pages')},
            {'name': 'map.administrativeregion', 'label': _('Region Importer')},
            {'name': 'map.mapdatacache', 'label': 'Map Data Cache (generated)'},
            {'name': 'map.vulnerabilitystatistic', 'label': 'Statistics (generated)'},
            {'name': 'map.highlevelstatistic', 'label': 'Organization statistics (generated)'},
            {'name': 'map.organizationreport'},
        ], 'permissions': ['admin']},

        {'app_label': 'organizations', 'label': _('🏢 Organizations'), 'items': [
            {'name': 'organization'},
            {'name': 'url'},
            # Promises have been replaced with comply or explain. On feature request they might return in the future.
            # The code is still in the system for this.
            # {'name': 'promise'},
            {'name': 'dataset', 'label': 'Data Set Import'},
            {'name': 'coordinate'},
            {'name': 'organizationtype'}
        ], 'permissions': ['admin']},

        {'label': _('🕒 Periodic Tasks'), 'items': [
            {'name': 'app.job'},
            {'name': 'django_celery_beat.periodictask'},
            {'name': 'django_celery_beat.crontabschedule'},
            # We support only crontabs as they deliver clear and concise information when the next scan will happen
            # This is not true for interval and solar, while they are easier to understand and read. It's unfortunate...
            # {'name': 'django_celery_beat.intervalschedule'},
            # {'name': 'django_celery_beat.solarschedule'},
        ], 'permissions': ['admin']},

        {'app_label': 'scanners', 'label': _('🔬 Scanning (generated)'), 'items': [
            {'name': 'endpoint', 'permissions': ['admin'], 'label': 'Endpoints'},
            {'name': 'endpointgenericscan', 'permissions': ['scanners.change_endpointgenericscan'],
             'label': 'Endpoint Scans'},
            {'name': 'urlgenericscan', 'permissions': ['scanners.change_urlgenericscan'], 'label': 'URL Scans'},
            {'name': 'internetnlscan', 'permissions': ['scanners.change_internetnlscan'],
             'label': 'Internet.nl Scans Tasks'},
            # tlsqualysscans have been merged with endpointgenericscans
            # {'name': 'tlsqualysscan', 'permissions': ['scanners.change_tlsqualysscan']},
            {'name': 'scanproxy', 'permissions': ['scanners.scanproxy'], 'label': 'Scan Proxies'},
            {'name': 'screenshot'},
            # UrlIP's are not used currently, they are stored but have no value.
            # {'name': 'urlip', 'permissions': ['admin']},
            {'name': 'tlsqualysscratchpad', 'permissions': ['admin'], 'label': 'Qualys Scans Debug'},
            {'name': 'endpointgenericscanscratchpad', 'permissions': ['admin'],
             'label': 'Endpoint Scans Debug'},
        ]},

        {'label': _('📄 Reporting (generated)'), 'items': [
            {'name': 'reporting.urlreport'},
        ], 'permissions': ['admin']},

        {'app_label': 'pro', 'label': _('⭐ Pro (beta)'), 'items': [
            {'name': 'account'},
            {'name': 'creditmutation'},
            {'name': 'urllist'},
            {'name': 'urllistreport'},
            {'name': 'rescanrequest'},
            {'name': 'failmaporganizationdatafeed'},
            {'name': 'urldatafeed'},
        ], 'permissions': ['admin']},

        {'app_label': 'game', 'label': _('👾️ The Game (beta)'), 'items': [
            {'name': 'contest'},
            {'name': 'team'},
            {'name': 'organizationsubmission'},
            {'label': _('New organizations'),
             'url': '/admin/game/organizationsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-5',
             'url_blank': False},
            {'name': 'urlsubmission'},
            {'label': _('New urls'),
             'url': '/admin/game/urlsubmission/?has_been_accepted__exact=0&has_been_rejected__exact=0&o=-6.2.3',
             'url_blank': False},
        ], 'permissions': ['admin']},

    ]
