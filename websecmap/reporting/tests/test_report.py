from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.reporting.report import (
    explanation_valid_around_this_moment,
    significant_moments,
    statistics_over_url_calculation,
)

# fit statements on one 120 char line.
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan

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
                    # this will be explained, its valid
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
                    # this explanation is not valid anymore, so will not be explained
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
                        "comply_or_explain_explanation_valid_until": isoformat("2023-02-22T10:45:06+00:00"),
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
            },
            # a copy of the above metrics, to see there is no copy-issue when calculating issues
            {
                "id": 981652,
                "concat": "https/443 IPv4",
                "ip": 4,
                "ip_version": 4,
                "port": 80,
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
                    # this will be explained, its valid
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
                    # this explanation is not valid anymore, so will not be explained
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
                        "comply_or_explain_explanation_valid_until": isoformat("2023-02-22T10:45:06+00:00"),
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
            },
        ],
    }

    # tls_qualys_certificate_trusted explanation is valid, so the stats should reflect that:
    calculation, amount_of_issues = statistics_over_url_calculation(
        ratings, at_when=datetime(2023, 4, 1, 1, tzinfo=timezone.utc)
    )

    assert calculation["endpoints"][0]["high"] == 0
    assert calculation["endpoints"][0]["medium"] == 0
    assert calculation["endpoints"][0]["low"] == 1
    # when OK is explained, it will be reduced from the normal totals, but its unusual and weird to explain an ok.
    assert calculation["endpoints"][0]["ok"] == 2
    # the low and high are both explained
    assert calculation["endpoints"][0]["explained_high"] == 1
    assert calculation["endpoints"][0]["explained_medium"] == 0
    assert calculation["endpoints"][0]["explained_low"] == 1

    # the second endpoint should have exactly the same metric data, only the port has changed.
    assert calculation["endpoints"][1]["high"] == 0
    assert calculation["endpoints"][1]["medium"] == 0
    assert calculation["endpoints"][1]["low"] == 1
    assert calculation["endpoints"][1]["ok"] == 2
    assert calculation["endpoints"][1]["explained_high"] == 1
    assert calculation["endpoints"][1]["explained_medium"] == 0
    assert calculation["endpoints"][1]["explained_low"] == 1

    # lets's see if these individual metrics are then summarized coorectly
    assert amount_of_issues["overall_explained"]["high"] == 2
    assert amount_of_issues["overall"]["high"] == 0

    # now the explanations are not valid anymore, so you'll see that it will be just another high
    calculation, amount_of_issues = statistics_over_url_calculation(
        ratings, at_when=datetime(2022, 4, 1, 1, tzinfo=timezone.utc)
    )
    assert amount_of_issues["overall_explained"]["high"] == 0
    assert amount_of_issues["overall"]["high"] == 2
    assert calculation["endpoints"][0]["explained_high"] == 0


def test_explanation_valid_around_this_moment():
    rating = {
        "is_explained": True,
        "comply_or_explain_explained_on": datetime(2022, 4, 1, 1, tzinfo=timezone.utc),
        "comply_or_explain_explanation_valid_until": datetime(2022, 5, 1, 1, tzinfo=timezone.utc),
    }
    # before the explanation is valid:
    assert explanation_valid_around_this_moment(rating, datetime(2022, 3, 31, tzinfo=timezone.utc)) is False

    # one day in the range is ok, day two of the month
    assert explanation_valid_around_this_moment(rating, datetime(2022, 4, 2, 1, tzinfo=timezone.utc)) is True

    # on the same day is ok, at the exact moment it starts
    # reports are usually made at the start of the day, which means that the explain could be valid later that day.
    # so explains are valid from the start of the day, regardless what the timestamp says.
    assert explanation_valid_around_this_moment(rating, datetime(2022, 4, 1, tzinfo=timezone.utc)) is True
    assert explanation_valid_around_this_moment(rating, datetime(2022, 4, 30, 23, 59, 59, tzinfo=timezone.utc)) is True

    assert explanation_valid_around_this_moment(rating, datetime(2022, 5, 1, 23, 59, 59, tzinfo=timezone.utc)) is True
    # explanation is lenient for one day, which might cause some slight deviations in stats
    assert explanation_valid_around_this_moment(rating, datetime(2022, 5, 2, tzinfo=timezone.utc)) is True

    assert explanation_valid_around_this_moment(rating, datetime(2022, 5, 3, tzinfo=timezone.utc)) is False

    # random sample from report where things go wrong
    assert (
        explanation_valid_around_this_moment(
            {
                "type": "ports",
                "explanation": "port_should_not_be_open",
                "evidence": "",
                "since": "2023-04-14T09:01:42+00:00",
                "last_scan": "2023-06-16T09:01:14+00:00",
                "high": 0,
                "medium": 1,
                "low": 0,
                "ok": 0,
                "not_testable": 0,
                "not_applicable": 0,
                "error_in_test": 0,
                "is_explained": True,
                "comply_or_explain_explanation": "policy_explanation_fits_cloudflare_open_port",
                "comply_or_explain_explained_on": "2023-05-08T15:08:36+00:00",
                "comply_or_explain_explanation_valid_until": "2026-02-01T15:08:36+00:00",
                "comply_or_explain_valid_at_time_of_report": True,
                "scan": 13373584,
                "scan_type": "ports",
            },
            datetime(2023, 6, 16, tzinfo=timezone.utc),
        )
        is True
    )


def test_significant_moments(db, default_scan_metadata, default_policy):
    # Creates events: a new url, a non-resolvable one and a dead one.
    url = Url.objects.create(
        url="test.nl",
        created_on=datetime(2022, 3, 30, tzinfo=timezone.utc),
        not_resolvable=True,
        not_resolvable_since=datetime(2023, 3, 30, tzinfo=timezone.utc),
        is_dead=True,
        is_dead_since=datetime(2023, 4, 30, tzinfo=timezone.utc),
    )

    # a standard HTTPS endpoint, while theurl was alive and resovlable
    first_endpoint = Endpoint.objects.create(
        url=url,
        protocol="https",
        port="443",
        ip_version=4,
        discovered_on=datetime(2022, 5, 30, tzinfo=timezone.utc),
        is_dead=True,
        # metric is within the period while it was alive
        is_dead_since=datetime(2022, 8, 30, tzinfo=timezone.utc),
    )

    epgs = EndpointGenericScan.objects.create(
        endpoint=first_endpoint,
        type="tls_qualys_encryption_quality",
        rating="A+",
        rating_determined_on=datetime(2022, 5, 30, tzinfo=timezone.utc),
        last_scan_moment=datetime(2022, 6, 30, tzinfo=timezone.utc),
        comply_or_explain_is_explained=False,
        is_the_latest_scan=True,
    )

    # also add a nice url
    ugs = UrlGenericScan.objects.create(
        url=url,
        type="dnssec",
        rating="ok",
        rating_determined_on=datetime(2022, 5, 30, tzinfo=timezone.utc),
        last_scan_moment=datetime(2022, 6, 30, tzinfo=timezone.utc),
        comply_or_explain_is_explained=False,
        is_the_latest_scan=True,
    )

    # we found an issue where a dead url could not be found when the following was used:
    # because str()/__str__ is called on the url, even though it is an url object. So database queries
    # contained † signs on dead urls... You don't search for the str of url but on the id to fix this.
    any_dead_url = Url.objects.filter(is_dead=True, id__in=[url.id])
    assert any_dead_url.count() == 1

    moments, happenings = significant_moments([url], ["tls_qualys_encryption_quality", "dnssec"])
    assert moments == [
        datetime(2022, 5, 30, 0, 0, 59, 999999, tzinfo=timezone.utc),
        datetime(2022, 8, 30, 0, 0, 59, 999999, tzinfo=timezone.utc),
        datetime(2023, 3, 30, 0, 0, 59, 999999, tzinfo=timezone.utc),
        datetime(2023, 4, 30, 0, 0, 59, 999999, tzinfo=timezone.utc),
    ]

    # before this bugfix the dead and non-revolvable urls would have been emtpy
    assert happenings["dead_endpoints"].first().id == first_endpoint.id
    assert happenings["dead_urls"].first().id == url.id
    assert happenings["non_resolvable_urls"].first().id == url.id
    assert happenings["endpoint_scans"] == [epgs]
    assert happenings["url_scans"] == [ugs]
