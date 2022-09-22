from websecmap.scanners import read_scan_config_from_file, SCANNERS_BY_ID
from websecmap.scanners.models import Scanner
from websecmap.scanners.scanmetadata import (
    get_scanners_for_backend,
    get_scanners_for_frontend,
    dump_scan_config_to_file,
)

import os


def test_dump_to_file(db, default_scan_metadata, tmpdir):
    # This makes the default policy also the one read by default.
    os.makedirs("scanmetadata_bootstrap_cache_writable_by_application", exist_ok=True)
    dump_scan_config_to_file()
    data = read_scan_config_from_file()
    assert data == get_scanners_for_backend()


def test_get_scanners_for_backend(db, default_scan_metadata):
    scanners = get_scanners_for_backend()

    assert len(scanners) > 10

    keys = [
        "can_discover_endpoints",
        "can_discover_urls",
        "can_scan_endpoints",
        "can_scan_urls",
        "can_verify_endpoints",
        "can_verify_urls",
        "creates_endpoint_scan_types",
        "creates_url_scan_types",
        "description",
        "id",
        "name",
        "needs_results_from",
        "plannable_activities",
    ]

    for key in keys:
        assert key in scanners[0]


def test_get_scanners_for_frontend(db, default_scan_metadata, default_policy):
    data = get_scanners_for_frontend()

    assert len(data) > 10

    keys = ["documentation links", "id", "name", "relevant impacts", "second opinion links", "category"]

    for key in keys:
        assert key in data["ftp"]


def test_do_scanner_ids_match(db, default_scan_metadata):
    # data = read_scan_config_from_file()

    for scanner in Scanner.objects.all():
        scanner_dict = SCANNERS_BY_ID[scanner.id]
        assert scanner_dict["python_name"] == scanner.python_name
