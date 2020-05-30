from datetime import datetime

from websecmap.reporting.severity import standard_calculation_for_internet_nl
from websecmap.scanners.models import EndpointGenericScan


def test_internet_nl_standard_calculation(db):

    now = datetime.now()

    # Api v1 does not have json content, api v2 does.
    scan = EndpointGenericScan()
    scan.explanation = "test"
    scan.rating_determined_on = now
    scan.last_scan_moment = now
    scan.type = "test"

    value = standard_calculation_for_internet_nl(scan, "", 0, 0, 0, False, False, False)

    assert value == {
        "type": "test",
        "explanation": "",
        "since": now.isoformat(),
        "last_scan": now.isoformat(),
        "high": 0,
        "medium": 0,
        "low": 0,

        # If all are 0, then it's ok.
        "ok": 1,
        "not_testable": False,
        "not_applicable": False,
        "error_in_test": False,
        'test_result': 0,
    }

    value = standard_calculation_for_internet_nl(scan, '{"translation": "test"}', 0, 0, 0, False, False, False)

    assert value == {
        "type": "test",
        "translation": "test",
        "explanation": '',
        "technical_details": 0,
        "since": now.isoformat(),
        "last_scan": now.isoformat(),
        "high": 0,
        "medium": 0,
        "low": 0,
        "ok": 1,
        "not_testable": False,
        "not_applicable": False,
        "error_in_test": False,
        'test_result': 0,
    }
