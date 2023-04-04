from datetime import datetime, timezone

from websecmap.reporting.severity import get_score_from_policy, internet_nl
from websecmap.scanners.models import EndpointGenericScan


def test_internet_nl_standard_calculation(db, default_policy):

    now = datetime.now(timezone.utc)

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
        "evidence": 0,
    }

    scan.explanation = '{"translation": "test"}'
    scan.evidence = "my_evidence"
    value = internet_nl(scan)

    assert value == {
        "translation": "test",
        "test_result": "failed",
        "evidence": "my_evidence",
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

    # special case for internet.nl scores:
    scan.type = "internet_nl_mail_dashboard_overall_score"
    # scan.explanation = "testing no crashes on non json data and overriding this value"
    # see that the translation still is carred on with it...
    scan.explanation = '{"translation": "test"}'
    # 42 in the default policy is well in the high risk range.
    scan.rating = "42"
    scan.evidence = "https://internet.nl/123123/scan/somethingsomethingsomethingdarkside"
    value = internet_nl(scan)
    assert value == {
        "translation": "test",
        "test_result": "42",
        "technical_details": "https://internet.nl/123123/scan/somethingsomethingsomethingdarkside",
        "type": "internet_nl_mail_dashboard_overall_score",
        "explanation": "42 https://internet.nl/123123/scan/somethingsomethingsomethingdarkside",
        "since": now.isoformat(),
        "last_scan": now.isoformat(),
        "evidence": "https://internet.nl/123123/scan/somethingsomethingsomethingdarkside",
        "high": 1,
        "medium": 0,
        "low": 0,
        "ok": 0,
        "not_testable": 0,
        "not_applicable": 0,
        "error_in_test": 0,
    }
