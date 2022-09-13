from datetime import datetime

from websecmap.reporting.severity import internet_nl, get_score_from_policy
from websecmap.scanners.models import EndpointGenericScan


def test_internet_nl_standard_calculation(db, default_policy):

    now = datetime.now()

    # Api v1 does not have json content, api v2 does.
    scan = EndpointGenericScan()
    scan.rating_determined_on = now
    scan.last_scan_moment = now
    scan.type = "internet_nl_web_https_tls_clientreneg"
    scan.rating = "failed"

    value = get_score_from_policy(scan)

    assert value == {
        "type": "internet_nl_web_https_tls_clientreneg",
        "explanation": "",
        "since": now.isoformat(),
        "last_scan": now.isoformat(),
        "high": 1,
        "medium": 0,
        "low": 0,
        # If all are 0, then it's ok.
        "ok": 0,
        "not_testable": 0,
        "not_applicable": 0,
        "error_in_test": 0,
    }

    scan.explanation = '{"translation": "test"}'
    scan.evidence = "my_evidence"
    value = internet_nl(scan)

    assert value == {
        "translation": "test",
        "test_result": "failed",
        "technical_details": "my_evidence",
        "type": "internet_nl_web_https_tls_clientreneg",
        "explanation": "",
        "since": now.isoformat(),
        "last_scan": now.isoformat(),
        "high": 1,
        "medium": 0,
        "low": 0,
        "ok": 0,
        "not_testable": 0,
        "not_applicable": 0,
        "error_in_test": 0,
    }
