from typing import Dict, Any
import json

default_app_config = "websecmap.scanners.apps.ScannersConfig"


def read_scan_config_from_file():
    # No try and except: just crash when things go south:
    bootstrap_file_location = "scanmetadata_bootstrap_cache_writable_by_application/constance_definitions.json"
    print(f"Attempting to read constance definitions from {bootstrap_file_location}.")

    try:
        with open(bootstrap_file_location, "rt") as handle:
            data = handle.read()
    except BaseException as exc:
        print(bootstrap_file_location)
        raise Exception from exc

    if not data:
        raise SystemError(
            "Scanner bootstrap configuration file does not contain data, cannot start application. "
            f"File being read: {bootstrap_file_location}"
        )

    return json.loads(data)


SCANNERS = read_scan_config_from_file()

ENDPOINT_SCAN_TYPES = []
URL_SCAN_TYPES = []
for scanner in SCANNERS:
    ENDPOINT_SCAN_TYPES = list(set(ENDPOINT_SCAN_TYPES + scanner["creates_endpoint_scan_types"]))
    URL_SCAN_TYPES = list(set(URL_SCAN_TYPES + scanner["creates_url_scan_types"]))

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# convert endpoint scan types to scanners, so we know what endpoint scan type belongs to what scanner
SCAN_TYPES_TO_SCANNER = {}
for scanner in SCANNERS:
    for scan_type in scanner["creates_endpoint_scan_types"]:
        SCAN_TYPES_TO_SCANNER[scan_type] = scanner

    for scan_type in scanner["creates_url_scan_types"]:
        SCAN_TYPES_TO_SCANNER[scan_type] = scanner

SCANNERS_BY_ID = {}
for scanner in SCANNERS:
    SCANNERS_BY_ID[scanner["id"]] = scanner

# It's impossible to know what ID you have as a scanner. We _CAN_ force it but we wont as it will become a mess.
SCANNERS_BY_PYTHON_NAME: Dict[str, Any] = {}
for scanner in SCANNERS:
    SCANNERS_BY_PYTHON_NAME[scanner["python_name"]] = scanner

SCANNERS_BY_PYTHON_NAME: Dict[str, Any] = {}
for scanner in SCANNERS:
    SCANNERS_BY_PYTHON_NAME[scanner["python_name"]] = scanner

SCANNERS_BY_SCAN_TYPE: Dict[str, Any] = {}
for scanner in SCANNERS:
    for epst in scanner["creates_endpoint_scan_types"]:
        SCANNERS_BY_SCAN_TYPE[epst] = scanner
    for epst in scanner["creates_url_scan_types"]:
        SCANNERS_BY_SCAN_TYPE[epst] = scanner

# todo: add config options for each of the scans defined above, include them in constance.
# todo: check these config options dynamically at the right moments, so to reduce maintenance.


def init_dict(*args):
    # To deal with the well known issues with mutable arguments in methods.
    # Initialize to empty dicts, so they can be used as kwargs and other constructs without having to deal with None
    # values all the time.

    returned = []

    for arg in args:
        if arg is None:
            returned.append({})
        else:
            returned.append(arg)

    if len(returned) == 1:
        return returned[0]

    return tuple(returned)
