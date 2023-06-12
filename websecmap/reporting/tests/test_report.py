from datetime import datetime, timezone

from websecmap.reporting.report import statistics_over_url_calculation

# fit statements on one 120 char line.
isoformat = datetime.fromisoformat


def test_statistics_over_url_calculation():
    ratings = {
        "url": "timetest.nl",
        "ratings": [],
        "endpoints": [
            {
                "id": 981652,
                "concat": "https/443 IPv4",
                "ip": 4,
                "ip_version": 4,
                "port": 443,
                "protocol": "https",
                "v4": True,
                "ratings": [
                    {
                        "type": "tls_qualys_certificate_trusted",
                        "explanation": "Certificate is not trusted.",
                        "evidence": "",
                        "since": "2022-09-14T01:23:46+00:00",
                        "last_scan": "2023-06-11T05:18:15+00:00",
                        "high": 1,
                        "medium": 0,
                        "low": 0,
                        "ok": 0,
                        "not_testable": 0,
                        "not_applicable": 0,
                        "error_in_test": 0,
                        "is_explained": True,
                        "comply_or_explain_explanation": "trusted_on_local_device_with_custom_trust_policy",
                        "comply_or_explain_explained_on": isoformat("2023-02-10T10:17:43+00:00"),
                        "comply_or_explain_explanation_valid_until": isoformat("2023-05-11T10:17:56+00:00"),
                        "comply_or_explain_valid_at_time_of_report": False,
                        "scan": 6928507,
                        "scan_type": "tls_qualys_certificate_trusted",
                    },
                    {
                        "type": "http_security_header_x_frame_options",
                        "explanation": "missing",
                        "evidence": "",
                        "since": "2022-09-17T01:31:19+00:00",
                        "last_scan": "2023-06-11T17:55:54+00:00",
                        "high": 0,
                        "medium": 0,
                        "low": 1,
                        "ok": 0,
                        "not_testable": 0,
                        "not_applicable": 0,
                        "error_in_test": 0,
                        "is_explained": True,
                        "comply_or_explain_explanation": "service_intended_for_devices_not_browsers",
                        "comply_or_explain_explained_on": isoformat("2023-02-20T10:45:06+00:00"),
                        "comply_or_explain_explanation_valid_until": isoformat("2033-02-17T10:45:06+00:00"),
                        "comply_or_explain_valid_at_time_of_report": True,
                        "scan": 7126202,
                        "scan_type": "http_security_header_x_frame_options",
                    },
                    {
                        "type": "http_security_header_strict_transport_security",
                        "explanation": "present",
                        "evidence": "max-age=31536000;includeSubDomains; preload",
                        "since": "2023-06-11T17:55:54+00:00",
                        "last_scan": "2023-06-11T17:55:54+00:00",
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                        "ok": 1,
                        "not_testable": 0,
                        "not_applicable": 0,
                        "error_in_test": 0,
                        "is_explained": False,
                        "comply_or_explain_explanation": "",
                        "comply_or_explain_explained_on": "",
                        "comply_or_explain_explanation_valid_until": "",
                        "comply_or_explain_valid_at_time_of_report": False,
                        "scan": 15971245,
                        "scan_type": "http_security_header_strict_transport_security",
                    },
                    {
                        "type": "http_security_header_x_content_type_options",
                        "explanation": "present",
                        "evidence": "nosniff",
                        "since": "2023-02-08T16:46:00+00:00",
                        "last_scan": "2023-06-11T17:55:54+00:00",
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                        "ok": 1,
                        "not_testable": 0,
                        "not_applicable": 0,
                        "error_in_test": 0,
                        "is_explained": True,
                        "comply_or_explain_explanation": "service_intended_for_devices_not_browsers",
                        "comply_or_explain_explained_on": isoformat("2023-02-20T10:45:06+00:00"),
                        "comply_or_explain_explanation_valid_until": isoformat("2033-02-17T10:45:06+00:00"),
                        "comply_or_explain_valid_at_time_of_report": True,
                        "scan": 11715852,
                        "scan_type": "http_security_header_x_content_type_options",
                    },
                    {
                        "type": "tls_qualys_encryption_quality",
                        "explanation": "Good Transport Security, rated A.",
                        "evidence": "",
                        "since": "2022-09-14T01:23:46+00:00",
                        "last_scan": "2023-06-11T05:18:15+00:00",
                        "high": 0,
                        "medium": 0,
                        "low": 0,
                        "ok": 1,
                        "not_testable": 0,
                        "not_applicable": 0,
                        "error_in_test": 0,
                        "is_explained": False,
                        "comply_or_explain_explanation": "",
                        "comply_or_explain_explained_on": "",
                        "comply_or_explain_explanation_valid_until": "",
                        "comply_or_explain_valid_at_time_of_report": False,
                        "scan": 6928508,
                        "scan_type": "tls_qualys_encryption_quality",
                    },
                ],
            }
        ],
    }

    # tls_qualys_certificate_trusted explanation is valid, so the stats should reflect that:
    calculation, amount_of_issues = statistics_over_url_calculation(
        ratings, at_when=datetime(2023, 4, 1, 1, tzinfo=timezone.utc)
    )
    assert amount_of_issues["overall_explained"]["high"] == 1
    assert amount_of_issues["overall"]["high"] == 0
    assert calculation["endpoints"][0]["explained_high"] == 1

    # now it's not valid anymore, so you'll see that it will be just another high
    calculation, amount_of_issues = statistics_over_url_calculation(
        ratings, at_when=datetime(2022, 4, 1, 1, tzinfo=timezone.utc)
    )
    assert amount_of_issues["overall_explained"]["high"] == 0
    assert amount_of_issues["overall"]["high"] == 1
    assert calculation["endpoints"][0]["explained_high"] == 0
