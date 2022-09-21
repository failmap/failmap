from websecmap.scanners import SCANNERS, ALL_SCAN_TYPES


# todo: read this from a dumped file or so instead of accessing the database.
# you can for example at startup check the file and the startup again after everything is loaded?
# And then give a warning you need to reload the thing when changing this. And include a standard file...


def add_scanner_fields(constance_config):
    """
    Add a series of configuration options depending on the scanners in websecmap.

    Allows for easier reuse in projects that import websecmap.

    :param constance_config:
    :return:
    """
    # Add rate limiting per scanner and activity:
    for scanner in SCANNERS:
        python_name = scanner['python_name']
        for plannable_activity in scanner["plannable_activities"]:
            variable_name = f"RATE_LIMIT_{python_name.upper()}_{plannable_activity.upper()}"
            constance_config[variable_name] = (
                500,
                f"Simultaneous {plannable_activity.upper()} tasks for {python_name.upper()}.",
                int,
            )

    # Generate Scanner Settings:
    for scanner in SCANNERS:
        python_name = scanner['python_name'].upper()

        scan_types = scanner["creates_endpoint_scan_types"] + scanner["creates_url_scan_types"]

        if scan_types:
            # No scanner options when there are no scan types, those are usually discovery scanners.
            scanner_config = {
                f"USE_SCANNER_{python_name}": (
                    True,
                    f"Do you want to use the {scanner['python_name']} scanner?",
                    bool,
                ),
            }
            constance_config = {**constance_config, **scanner_config}

        if scanner["can_discover_endpoints"]:
            scanner_config = {
                f"DISCOVER_ENDPOINTS_USING_{python_name}": (
                    True,
                    f"Do you want to discover endpoints using the {python_name} scanner?",
                    bool,
                ),
            }
            constance_config = {**constance_config, **scanner_config}

        if scanner["can_discover_urls"]:
            scanner_config = {
                f"DISCOVER_URLS_USING_{python_name}": (
                    True,
                    f"Do you want to discover urls using the {python_name} scanner?",
                    bool,
                ),
            }
            constance_config = {**constance_config, **scanner_config}

        for scan_type in scanner["creates_endpoint_scan_types"] + scanner["creates_url_scan_types"]:
            scanner_config = {
                f"REPORT_INCLUDE_{scan_type.upper()}": (
                    True,
                    f"Do you want to add {scan_type} issues to the report?",
                    bool,
                ),
            }
            constance_config = {**constance_config, **scanner_config}

        for scan_type in scanner["creates_endpoint_scan_types"] + scanner["creates_url_scan_types"]:
            scanner_config = {
                f"SHOW_{scan_type.upper()}": (True, f"Do you want to show {scan_type} issues on the website?", bool),
            }
            constance_config = {**constance_config, **scanner_config}

    return constance_config


def add_scanner_fieldsets(constance_config_fieldsets):
    # now create the menus for these scanners.
    discover_set = ("SCAN_AT_ALL",)
    for scanner in SCANNERS:
        if scanner["can_discover_urls"]:
            discover_set += (f"DISCOVER_URLS_USING_{scanner['python_name'].upper()}",)

    for scanner in SCANNERS:
        if scanner["can_discover_endpoints"]:
            discover_set += (f"DISCOVER_ENDPOINTS_USING_{scanner['python_name'].upper()}",)

    scanner_config_set = []
    for scanner in SCANNERS:

        scan_types = scanner["creates_endpoint_scan_types"] + scanner["creates_url_scan_types"]
        if not scan_types:
            continue

        options = (f"USE_SCANNER_{scanner['python_name'].upper()}",)

        for scan_type in scan_types:
            options += (f"REPORT_INCLUDE_{scan_type.upper()}",)

        for scan_type in scan_types:
            options += (f"SHOW_{scan_type.upper()}",)

        scanner_config_per_scanner = (scanner["python_name"], options)
        scanner_config_set += (scanner_config_per_scanner,)

    constance_config_fieldsets.update(
        [
            ("Discovery of new urls, endpoints and scanning", discover_set),
        ]
    )

    constance_config_fieldsets.update(scanner_config_set)

    # Add rate limiting per scanner and activity:
    rate_limit = ()
    for scanner in SCANNERS:
        for plannable_activity in scanner["plannable_activities"]:
            variable_name = f"RATE_LIMIT_{scanner['python_name'].upper()}_{plannable_activity.upper()}"
            rate_limit += (variable_name,)

    constance_config_fieldsets.update(
        [
            ("Rate limit simultaneous activities per scanner", rate_limit),
        ]
    )

    return constance_config_fieldsets
