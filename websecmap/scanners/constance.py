from websecmap.scanners import SCANNERS


def add_scanner_fields(constance_config):
    """
    Add a series of configuration options depending on the scanners in websecmap.

    Allows for easier reuse in projects that import websecmap.

    :param constance_config:
    :return:
    """

    # Generate Scanner Settings:
    for scanner in SCANNERS:

        scan_types = scanner['creates endpoint scan types'] + scanner['creates url scan types']

        if scan_types:
            # No scanner options when there are no scan types, those are usually discovery scanners.
            scanner_config = {
                'USE_SCANNER_%s' % scanner['name'].upper():
                    (True, 'Do you want to use the %s scanner?' % scanner['name'], bool),
            }
            constance_config = {**constance_config, **scanner_config}

        if scanner['can discover endpoints']:
            scanner_config = {
                'DISCOVER_ENDPOINTS_USING_%s' % scanner['name'].upper(): (
                    True, 'Do you want to discover endpoints using the %s scanner?' % scanner['name'], bool),
            }
            constance_config = {**constance_config, **scanner_config}

        if scanner['can discover urls']:
            scanner_config = {
                'DISCOVER_URLS_USING_%s' % scanner['name'].upper(): (
                    True, 'Do you want to discover urls using the %s scanner?' % scanner['name'], bool),
            }
            constance_config = {**constance_config, **scanner_config}

        for scan_type in scanner['creates endpoint scan types'] + scanner['creates url scan types']:
            scanner_config = {
                'REPORT_INCLUDE_%s' % scan_type.upper():
                    (True, 'Do you want to add %s issues to the report?' % scan_type, bool),
            }
            constance_config = {**constance_config, **scanner_config}

        for scan_type in scanner['creates endpoint scan types'] + scanner['creates url scan types']:
            scanner_config = {
                'SHOW_%s' % scan_type.upper():
                    (True, 'Do you want to show %s issues on the website?' % scan_type, bool),
            }
            constance_config = {**constance_config, **scanner_config}

    return constance_config


def add_scanner_fieldsets(constance_config_fieldsets):
    # now create the menus for these scanners.
    discover_set = ('SCAN_AT_ALL',)
    for scanner in SCANNERS:
        if scanner['can discover urls']:
            discover_set += ('DISCOVER_URLS_USING_%s' % scanner['name'].upper(),)

    for scanner in SCANNERS:
        if scanner['can discover endpoints']:
            discover_set += ('DISCOVER_ENDPOINTS_USING_%s' % scanner['name'].upper(),)

    scanner_config_set = []
    for scanner in SCANNERS:

        scan_types = scanner['creates endpoint scan types'] + scanner['creates url scan types']
        if not scan_types:
            continue

        options = ('USE_SCANNER_%s' % scanner['name'].upper(),)

        for scan_type in scanner['creates endpoint scan types'] + scanner['creates url scan types']:
            options += ('REPORT_INCLUDE_%s' % scan_type.upper(),)

        for scan_type in scanner['creates endpoint scan types'] + scanner['creates url scan types']:
            options += ('SHOW_%s' % scan_type.upper(),)

        scanner_config_per_scanner = (scanner['verbose name'], options)
        scanner_config_set += (scanner_config_per_scanner,)

    constance_config_fieldsets.update([
        ('Discovery of new urls, endpoints and scanning', discover_set),
    ])

    constance_config_fieldsets.update(scanner_config_set)

    return constance_config_fieldsets
