# this will be moved to __init__.py
def read_scan_config_from_file():
    # No try and except: just crash when things go south:
    try:
        with open("scanmetadata_bootstrap_cache_writable_by_application/constance_definitions.json", "rt") as handle:
            data = handle.read()
    except BaseException as exc:
        print("Error opening scan metadata file in scanmetadata_bootstrap_cache/constance_definitions.json.")
        raise Exception from exc

    return data
