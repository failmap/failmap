from websecmap.app.constance import get_all_values
from websecmap.scanners.models import Scanner
from websecmap.scanners.scanmetadata import (
    get_scanners_for_backend,
    get_scanners_for_frontend,
    get_backend_scanmetadata,
)


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
    data = get_scanners_for_frontend(get_all_values())

    assert len(data) > 10

    keys = ["documentation links", "id", "name", "relevant impacts", "second opinion links", "category"]

    for key in keys:
        assert key in data["ftp"]


def test_do_scanner_ids_match(db, default_scan_metadata):
    metadata = get_backend_scanmetadata()

    for scanner in Scanner.objects.all():
        scanner_dict = metadata["scanners_by_id"][scanner.id]
        assert scanner_dict["python_name"] == scanner.python_name
