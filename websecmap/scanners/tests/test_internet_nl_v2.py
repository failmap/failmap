import logging
from copy import copy
from datetime import datetime, timedelta

from websecmap.organizations.models import Url
from websecmap.reporting.report import create_timeline, create_url_report
from websecmap.scanners.models import Endpoint, EndpointGenericScan, InternetNLV2Scan, InternetNLV2StateLog
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.internet_nl_v2_websecmap import (
    add_calculation,
    calculate_forum_standaardisatie_views_mail,
    calculate_forum_standaardisatie_views_web,
    initialize_scan,
    lowest_value_in_results,
    process_scan_results,
    progress_running_scan,
    update_state,
    reuse_last_fields_and_set_them_to_error,
)

log = logging.getLogger("websecmap")


def test_reuse_last_fields_and_set_them_to_error(db):
    url, created = Url.objects.all().get_or_create(url="example.nl")
    endpoint, created = Endpoint.objects.all().get_or_create(port=443, protocol="http", ip_version=4, url=url)

    # nothing happens, no crash etc.
    reuse_last_fields_and_set_them_to_error(endpoint)

    store_endpoint_scan_result(scan_type="test1", endpoint=endpoint, rating="some_value", message="")
    store_endpoint_scan_result(scan_type="test2", endpoint=endpoint, rating="some_value", message="")
    store_endpoint_scan_result(scan_type="test3", endpoint=endpoint, rating="some_value", message="")
    store_endpoint_scan_result(scan_type="test4", endpoint=endpoint, rating="some_value", message="")
    store_endpoint_scan_result(scan_type="test5", endpoint=endpoint, rating="some_value", message="")
    store_endpoint_scan_result(scan_type="test1", endpoint=endpoint, rating="some_value", message="")

    # add some values that should not be changed:
    safe_ep, created = Endpoint.objects.all().get_or_create(port=443, protocol="http", ip_version=6, url=url)
    store_endpoint_scan_result(scan_type="test1", endpoint=safe_ep, rating="some_value", message="")

    # more values that should not be changed:
    safe_ep, created = Endpoint.objects.all().get_or_create(port=0, protocol="dns", ip_version=6, url=url)
    store_endpoint_scan_result(scan_type="test1", endpoint=safe_ep, rating="some_value", message="")

    reuse_last_fields_and_set_them_to_error(endpoint)

    # 7 from above (note 1 is overwritten), and 5 overwritten with error.
    assert EndpointGenericScan.objects.all().count() == 7 + 5
    assert EndpointGenericScan.objects.all().filter(rating="error").count() == 5


def test_internet_nl_logging(db):

    # todo: make sure that never an empty list is added in normal situations?
    scan = initialize_scan("web", [])
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested"

    update_state(scan, "testing", "just a test")
    update_state(scan, "error", "an irrecoverable error occurred")

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "error"

    # requested plus two above states
    assert InternetNLV2StateLog.objects.all().count() == 3

    # a progressed scan will not do anything, as there is no recoverable state.
    progress_running_scan(scan)
    assert InternetNLV2StateLog.objects.all().count() == 3

    # a recoverable error will make sure the last known correct state is set, which is requested...
    update_state(
        scan,
        "configuration_error",
        "This is a recoverable error, and when progressing, the first valid state" "will be requested",
    )

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "configuration_error"

    # make sure you have the last information in the database
    scan = InternetNLV2Scan.objects.all().first()
    progress_running_scan(scan)
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested"

    # configuration_error + retry of requested
    assert InternetNLV2StateLog.objects.all().count() == 5

    # registering has a timeout of a few days, so let's time it out and check for it.
    # The timeout will be fixed next progression.
    update_state(scan, "registering", "This will take too long and time out.")
    scan.last_state_change = datetime.now() - timedelta(days=100)
    scan.save()
    progress_running_scan(scan)
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "timeout"

    # The timeout if fixed and a retry performed. The state is registering again.
    scan = InternetNLV2Scan.objects.all().first()
    progress_running_scan(scan)
    scan = InternetNLV2Scan.objects.all().first()
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested" == scan.state

    # now create another error situation whereby a different recoverable error is used than requested.
    update_state(
        scan, "running scan", "When an error occurs, a progress will move to running scan, and not to " "requested"
    )
    update_state(scan, "configuration_error", "oh no!")
    progress_running_scan(scan)

    # recoverable state, error and retry of recoverable state
    assert InternetNLV2StateLog.objects.all().count() == 11

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "running scan"


def test_internet_nl_store_testresults(db):
    test_results = {
        "secure.aalten.nl": {
            "status": "ok",
            "report": {"url": "https://dev.batch.internet.nl/site/secure.aalten.nl/665357/"},
            "scoring": {"percentage": 48},
            "results": {
                "categories": {
                    "web_ipv6": {"verdict": "failed", "status": "failed"},
                    "web_dnssec": {"verdict": "passed", "status": "passed"},
                    "web_https": {"verdict": "failed", "status": "failed"},
                    "web_appsecpriv": {"verdict": "warning", "status": "warning"},
                },
                "tests": {
                    "web_ipv6_ns_address": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [
                            ["ns2.transip.eu.", "2a01:7c8:f:c1f::195", "37.97.199.195"],
                            ["ns0.transip.net.", "2a01:7c8:dddd:195::195", "195.135.195.195"],
                            ["ns1.transip.nl.", "2a01:7c8:7000:195::195", "195.8.195.195"],
                        ],
                    },
                    "web_ipv6_ns_reach": {"status": "passed", "verdict": "good", "technical_details": []},
                    "web_ipv6_ws_address": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": [["secure.aalten.nl", "None", "None"]],
                    },
                    "web_ipv6_ws_reach": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_ipv6_ws_similar": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_dnssec_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["secure.aalten.nl", "None"]],
                    },
                    "web_dnssec_valid": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["secure.aalten.nl", "secure"]],
                    },
                    "web_https_http_available": {"status": "failed", "verdict": "bad", "technical_details": []},
                    "web_https_http_redirect": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_http_hsts": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_http_compress": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_tls_keyexchange": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_tls_ciphers": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_tls_cipherorder": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_tls_version": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_tls_compress": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_tls_secreneg": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_tls_clientreneg": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_https_cert_chain": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_cert_pubkey": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_cert_sig": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_cert_domain": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_dane_exist": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_dane_valid": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_tls_0rtt": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_tls_ocsp": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_https_tls_keyexchangehash": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_appsecpriv_x_frame_options": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_appsecpriv_referrer_policy": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_appsecpriv_csp": {"status": "not_tested", "verdict": "not-tested", "technical_details": []},
                    "web_appsecpriv_x_content_type_options": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                    "web_appsecpriv_x_xss_protection": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [],
                    },
                },
                "custom": {"tls_1_3_support": "yes"},
            },
        },
        "lyncdiscover.vng.nl": {
            "report": {"url": "https://dev.batch.internet.nl/site/lyncdiscover.vng.nl/665166/"},
            "status": "ok",
            "scoring": {"percentage": 66},
            "results": {
                "categories": {
                    "web_ipv6": {"verdict": "passed", "status": "passed"},
                    "web_dnssec": {"verdict": "failed", "status": "failed"},
                    "web_https": {"verdict": "failed", "status": "failed"},
                    "web_appsecpriv": {"verdict": "warning", "status": "warning"},
                },
                "tests": {
                    "web_ipv6_ns_address": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [
                            ["ns3.yourdomainprovider.net.", "2604:a880:800:10::9a1:2001", "104.236.29.251"],
                            ["ns1.yourdomainprovider.net.", "2a01:448:1::65:53", "213.249.65.53"],
                            ["ns2.yourdomainprovider.net.", "2a03:b0c0:3:d0::124:5001", "46.101.153.24"],
                        ],
                    },
                    "web_ipv6_ns_reach": {"status": "passed", "verdict": "good", "technical_details": []},
                    "web_ipv6_ws_address": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["lyncdiscover.vng.nl", "2603:1027::e", "52.112.193.16"]],
                    },
                    "web_ipv6_ws_reach": {"status": "passed", "verdict": "good", "technical_details": []},
                    "web_ipv6_ws_similar": {"status": "passed", "verdict": "good", "technical_details": []},
                    "web_dnssec_exist": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": [["lyncdiscover.vng.nl", "None"]],
                    },
                    "web_dnssec_valid": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [["lyncdiscover.vng.nl", "insecure"]],
                    },
                    "web_https_http_available": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "yes"], ["52.112.196.45", "yes"]],
                    },
                    "web_https_http_redirect": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "no"], ["52.112.196.45", "no"]],
                    },
                    "web_https_http_hsts": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_https_http_compress": {
                        "status": "info",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "yes"], ["52.112.196.45", "yes"]],
                    },
                    "web_https_tls_keyexchange": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_https_tls_ciphers": {
                        "status": "warning",
                        "verdict": "phase-out",
                        "technical_details": [
                            ["2603:1027::e", "AES128-GCM-SHA256", "phase out"],
                            ["...", "AES128-SHA256", "phase out"],
                            ["...", "AES256-SHA", "phase out"],
                            ["...", "AES128-SHA", "phase out"],
                            ["...", "AES256-SHA256", "phase out"],
                            ["...", "AES256-GCM-SHA384", "phase out"],
                            ["52.112.196.45", "AES128-GCM-SHA256", "phase out"],
                            ["...", "AES128-SHA256", "phase out"],
                            ["...", "AES256-SHA", "phase out"],
                            ["...", "AES128-SHA", "phase out"],
                            ["...", "AES256-SHA256", "phase out"],
                            ["...", "AES256-GCM-SHA384", "phase out"],
                        ],
                    },
                    "web_https_tls_cipherorder": {
                        "status": "warning",
                        "verdict": "warning",
                        "technical_details": [
                            ["2603:1027::e", "ECDHE-RSA-AES128-SHA256", " "],
                            ["...", "ECDHE-RSA-AES256-SHA", 4],
                            ["52.112.196.45", "ECDHE-RSA-AES128-SHA256", " "],
                            ["...", "ECDHE-RSA-AES256-SHA", 4],
                        ],
                    },
                    "web_https_tls_version": {
                        "status": "warning",
                        "verdict": "phase-out",
                        "technical_details": [
                            ["2603:1027::e", "TLS 1.1", "phase out"],
                            ["...", "TLS 1.0", "phase out"],
                            ["52.112.196.45", "TLS 1.1", "phase out"],
                            ["...", "TLS 1.0", "phase out"],
                        ],
                    },
                    "web_https_tls_compress": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "no"], ["52.112.196.45", "no"]],
                    },
                    "web_https_tls_secreneg": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "yes"], ["52.112.196.45", "yes"]],
                    },
                    "web_https_tls_clientreneg": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "no"], ["52.112.196.45", "no"]],
                    },
                    "web_https_cert_chain": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_https_cert_pubkey": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_https_cert_sig": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_https_cert_domain": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": [
                            ["2603:1027::e", "*.online.lync.com"],
                            ["...", "meet.lync.com"],
                            ["...", "*.infra.lync.com"],
                            ["...", "sched.lync.com"],
                            ["...", "*.lync.com"],
                            ["52.112.196.45", "*.online.lync.com"],
                            ["...", "meet.lync.com"],
                            ["...", "*.infra.lync.com"],
                            ["...", "sched.lync.com"],
                            ["...", "*.lync.com"],
                        ],
                    },
                    "web_https_dane_exist": {
                        "status": "info",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "no"], ["52.112.196.45", "no"]],
                    },
                    "web_https_dane_valid": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": [["2603:1027::e", "not tested"], ["52.112.196.45", "not tested"]],
                    },
                    "web_https_tls_0rtt": {
                        "status": "passed",
                        "verdict": "na",
                        "technical_details": [["2603:1027::e", "no"], ["52.112.196.45", "no"]],
                    },
                    "web_https_tls_ocsp": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "yes"], ["52.112.196.45", "yes"]],
                    },
                    "web_https_tls_keyexchangehash": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "yes"], ["52.112.196.45", "yes"]],
                    },
                    "web_appsecpriv_x_frame_options": {
                        "status": "warning",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_appsecpriv_referrer_policy": {
                        "status": "warning",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_appsecpriv_csp": {
                        "status": "info",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                    "web_appsecpriv_x_content_type_options": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": [["2603:1027::e", "nosniff"], ["52.112.196.45", "nosniff"]],
                    },
                    "web_appsecpriv_x_xss_protection": {
                        "status": "warning",
                        "verdict": "bad",
                        "technical_details": [["2603:1027::e", "None"], ["52.112.196.45", "None"]],
                    },
                },
                "custom": {"tls_1_3_support": "yes"},
            },
        },
    }

    scan = InternetNLV2Scan()
    scan.retrieved_scan_report = test_results
    scan.type = "web"
    scan.save()

    # make sure there are records to attach these scan results to:
    url1 = Url()
    url1.url = "secure.aalten.nl"
    url1.save()

    endpoint1 = Endpoint()
    endpoint1.url = url1
    endpoint1.protocol = "dns_a_aaaa"
    endpoint1.port = 0
    endpoint1.ip_version = 4
    endpoint1.save()

    url2 = Url()
    url2.url = "lyncdiscover.vng.nl"
    url2.save()

    endpoint2 = Endpoint()
    endpoint2.url = url2
    endpoint2.protocol = "dns_a_aaaa"
    endpoint2.port = 0
    endpoint2.ip_version = 4
    endpoint2.save()

    process_scan_results(scan)

    create_url_report(create_timeline(url1), url1)
    create_url_report(create_timeline(url2), url2)

    # is there a series of imports?
    assert EndpointGenericScan.objects.all().count() == 94

    # are the web scans imported
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_appsecpriv_x_xss_protection").count() == 2

    # have the legacy views run?
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_legacy_dnssec").count() == 2

    # The categories are imported
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_ipv6").count() == 2

    # The new fields of api v2.0 have been imported:
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_https_tls_cipherorder").count() == 2
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_https_tls_0rtt").count() == 2
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_https_tls_ocsp").count() == 2
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_https_tls_keyexchangehash").count() == 2

    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_legacy_tls_1_3").count() == 2

    scan_data = test_results["lyncdiscover.vng.nl"]

    # passed, failed = failed
    assert lowest_value_in_results(scan_data, ["web_ipv6_ws_reach", "web_dnssec_exist"]) == "failed"

    # not_tested, failed
    assert lowest_value_in_results(scan_data, ["web_dnssec_valid", "web_dnssec_exist"]) == "failed"

    # warning, passed
    assert lowest_value_in_results(scan_data, ["web_https_tls_ciphers", "web_ipv6_ws_reach"]) == "warning"

    # passed, warning, flip it around.
    assert lowest_value_in_results(scan_data, ["web_ipv6_ws_reach", "web_https_tls_ciphers"]) == "warning"

    # passed, passed, passed, passed, passed, failed, passed, passed
    assert (
        lowest_value_in_results(
            scan_data,
            [
                "web_ipv6_ws_reach",
                "web_ipv6_ws_reach",
                "web_ipv6_ws_reach",
                "web_ipv6_ws_reach",
                "web_ipv6_ws_reach",
                "web_dnssec_exist",
                "web_ipv6_ws_reach",
                "web_ipv6_ws_reach",
            ],
        )
        == "failed"
    )

    # store mail scan results:
    mail_results = {
        "dommel.nl": {
            "status": "ok",
            "report": {"url": "https://dev.batch.internet.nl/mail/dommel.nl/287994/"},
            "scoring": {"percentage": 83},
            "results": {
                "categories": {
                    "mail_ipv6": {"verdict": "failed", "status": "failed"},
                    "mail_dnssec": {"verdict": "passed", "status": "passed"},
                    "mail_auth": {"verdict": "passed", "status": "passed"},
                    "mail_starttls": {"verdict": "failed", "status": "failed"},
                },
                "tests": {
                    "mail_ipv6_ns_address": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [
                                ["ns1.qsp.nl.", "2a04:c580:0:f0::1", "193.254.215.240"],
                                ["ns2.qsp.nl.", "2a04:c580:0:f1::1", "193.254.215.241"],
                            ]
                        },
                    },
                    "mail_ipv6_ns_reach": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": []},
                    },
                    "mail_ipv6_mx_address": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": {
                            "data_matrix": [
                                ["mail.dommel.nl.", "None", "81.175.72.228"],
                                ["fallback.dommel.nl.", "None", "89.106.167.130"],
                            ]
                        },
                    },
                    "mail_ipv6_mx_reach": {
                        "status": "not_tested",
                        "verdict": "not-tested",
                        "technical_details": {"data_matrix": []},
                    },
                    "mail_dnssec_mailto_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": [["dommel.nl", "None"]]},
                    },
                    "mail_dnssec_mailto_valid": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": [["dommel.nl", "secure"]]},
                    },
                    "mail_dnssec_mx_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["mail.dommel.nl.", "yes"], ["fallback.dommel.nl.", "yes"]]
                        },
                    },
                    "mail_dnssec_mx_valid": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["mail.dommel.nl.", "secure"], ["fallback.dommel.nl.", "secure"]]
                        },
                    },
                    "mail_auth_dmarc_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarcreports@dommel.nl;"]]
                        },
                    },
                    "mail_auth_dmarc_policy": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": []},
                    },
                    "mail_auth_dkim_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": []},
                    },
                    "mail_auth_spf_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [
                                ["v=spf1 ip4:81.175.72.228 ip4:85.17.2.13 ip4:46.31.48.0/21 a:fallback.dommel.nl -all"]
                            ]
                        },
                    },
                    "mail_auth_spf_policy": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {"data_matrix": []},
                    },
                    "mail_starttls_tls_available": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "yes"], ["mail.dommel.nl.", "yes"]]
                        },
                    },
                    "mail_starttls_tls_keyexchange": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": {
                            "data_matrix": [
                                ["fallback.dommel.nl.", "DH-2048", "insufficient"],
                                ["mail.dommel.nl.", "None"],
                            ]
                        },
                    },
                    "mail_starttls_tls_ciphers": {
                        "status": "warning",
                        "verdict": "phase-out",
                        "technical_details": {
                            "data_matrix": [
                                ["fallback.dommel.nl.", "AES256-GCM-SHA384", "phase out"],
                                ["mail.dommel.nl.", "None"],
                            ]
                        },
                    },
                    "mail_starttls_tls_cipherorder": {
                        "status": "failed",
                        "verdict": "bad",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "None"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_tls_version": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "None"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_tls_compress": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "no"], ["mail.dommel.nl.", "no"]]
                        },
                    },
                    "mail_starttls_tls_secreneg": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "yes"], ["mail.dommel.nl.", "yes"]]
                        },
                    },
                    "mail_starttls_tls_clientreneg": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "no"], ["mail.dommel.nl.", "no"]]
                        },
                    },
                    "mail_starttls_cert_chain": {
                        "status": "info",
                        "verdict": "bad",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "fallback.dommel.nl"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_cert_pubkey": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "None"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_cert_sig": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "None"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_cert_domain": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "None"], ["mail.dommel.nl.", "None"]]
                        },
                    },
                    "mail_starttls_dane_exist": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [
                                [
                                    "fallback.dommel.nl.",
                                    "3 0 1 7E27A55454560F21B829DC501691C6780A086A445FF549DC36065BE43896FB17",
                                ],
                                [
                                    "mail.dommel.nl.",
                                    "3 0 1 002E3C83A3EC137AA0C395F32AD3C3DDAF68DECE6F8AE9066AF1DA62554E53DE",
                                ],
                            ]
                        },
                    },
                    "mail_starttls_dane_valid": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "yes"], ["mail.dommel.nl.", "yes"]]
                        },
                    },
                    "mail_starttls_dane_rollover": {
                        "status": "info",
                        "verdict": "bad",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "no"], ["mail.dommel.nl.", "no"]]
                        },
                    },
                    "mail_starttls_tls_0rtt": {
                        "status": "passed",
                        "verdict": "na",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "no"], ["mail.dommel.nl.", "no"]]
                        },
                    },
                    "mail_starttls_tls_keyexchangehash": {
                        "status": "passed",
                        "verdict": "good",
                        "technical_details": {
                            "data_matrix": [["fallback.dommel.nl.", "yes"], ["mail.dommel.nl.", "yes"]]
                        },
                    },
                },
                # mail non sending domain is True, so we can check that the dkim value form issue #183 will prevail
                # over the data returned.
                "custom": {
                    "mail_non_sending_domain": True,
                    "mail_servers_testable_status": "no_mx",
                    "tls_1_3_support": "no",
                },
            },
        }
    }

    # special no_mx state for mail_servers_testable is set above.

    scan = InternetNLV2Scan()
    scan.retrieved_scan_report = mail_results
    scan.type = "mail_dashboard"
    scan.save()

    url1 = Url()
    url1.url = "dommel.nl"
    url1.save()

    endpoint1 = Endpoint()
    endpoint1.url = url1
    endpoint1.protocol = "dns_soa"
    endpoint1.port = 0
    endpoint1.ip_version = 4
    endpoint1.save()

    process_scan_results(scan)

    assert EndpointGenericScan.objects.all().filter(type="internet_nl_mail_starttls_dane_rollover").count() == 1

    assert EndpointGenericScan.objects.all().filter(type="internet_nl_mail_legacy_tls_1_3").count() == 1

    assert EndpointGenericScan.objects.all().filter(type="internet_nl_mail_legacy_start_tls_ncsc").count() == 1

    assert EndpointGenericScan.objects.all().filter(type="internet_nl_mail_legacy_category_ipv6").count() == 1

    assert EndpointGenericScan.objects.all().filter(type="nonsense").count() == 0

    # +1 due to adding mail_sending_domain
    assert EndpointGenericScan.objects.all().count() == 94 + 53 + 1

    create_url_report(create_timeline(url1), url1)


def test_legacy_calculations():
    mail_results = {
        "dommel.nl": {
            "status": "ok",
            "report": {"url": "https://dev.batch.internet.nl/mail/dommel.nl/287994/"},
            "scoring": {"percentage": 83},
            "results": {
                "categories": {
                    "mail_ipv6": {"verdict": "failed", "status": "failed"},
                    "mail_dnssec": {"verdict": "passed", "status": "passed"},
                    "mail_auth": {"verdict": "passed", "status": "passed"},
                    "mail_starttls": {"verdict": "failed", "status": "failed"},
                },
                "tests": {
                    "mail_ipv6_ns_address": {"status": "passed", "verdict": "good"},
                    "mail_ipv6_ns_reach": {"status": "passed", "verdict": "good"},
                    # Setup for: https://github.com/internetstandards/Internet.nl-dashboard/issues/184
                    "mail_ipv6_mx_address": {"status": "failed", "verdict": "bad"},
                    "mail_ipv6_mx_reach": {"status": "not_tested", "verdict": "not-tested"},
                    "mail_dnssec_mailto_exist": {"status": "passed", "verdict": "good"},
                    "mail_dnssec_mailto_valid": {"status": "passed", "verdict": "good"},
                    "mail_dnssec_mx_exist": {"status": "passed", "verdict": "good"},
                    "mail_dnssec_mx_valid": {"status": "passed", "verdict": "good"},
                    "mail_auth_dmarc_exist": {"status": "passed", "verdict": "good"},
                    "mail_auth_dmarc_policy": {"status": "passed", "verdict": "good"},
                    "mail_auth_dkim_exist": {"status": "passed", "verdict": "good"},
                    "mail_auth_spf_exist": {"status": "passed", "verdict": "good"},
                    "mail_auth_spf_policy": {"status": "not_tested", "verdict": "good"},
                    "mail_starttls_tls_available": {"status": "passed", "verdict": "good"},
                    "mail_starttls_tls_keyexchange": {"status": "failed", "verdict": "bad"},
                    "mail_starttls_tls_ciphers": {"status": "warning", "verdict": "phase-out"},
                    "mail_starttls_tls_cipherorder": {"status": "failed", "verdict": "bad"},
                    "mail_starttls_tls_version": {"status": "passed", "verdict": "good"},
                    "mail_starttls_tls_compress": {"status": "passed", "verdict": "good"},
                    "mail_starttls_tls_secreneg": {"status": "passed", "verdict": "good"},
                    "mail_starttls_tls_clientreneg": {"status": "passed", "verdict": "good"},
                    "mail_starttls_cert_chain": {"status": "info", "verdict": "bad"},
                    "mail_starttls_cert_pubkey": {"status": "passed", "verdict": "good"},
                    "mail_starttls_cert_sig": {"status": "passed", "verdict": "good"},
                    "mail_starttls_cert_domain": {"status": "passed", "verdict": "good"},
                    "mail_starttls_dane_exist": {"status": "passed", "verdict": "good"},
                    "mail_starttls_dane_valid": {"status": "passed", "verdict": "good"},
                    "mail_starttls_dane_rollover": {"status": "info", "verdict": "bad"},
                    "mail_starttls_tls_0rtt": {"status": "passed", "verdict": "na"},
                    "mail_starttls_tls_keyexchangehash": {"status": "passed", "verdict": "good"},
                },
                # mail non sending domain is True, so we can check that the dkim value form issue #183 will prevail
                # over the data returned.
                "custom": {
                    "mail_non_sending_domain": True,
                    "mail_servers_testable_status": "no_mx",
                    "tls_1_3_support": "no",
                },
            },
        },
        "www.zundert.nl": {
            "status": "ok",
            "report": {"url": "https://dev.batch.internet.nl/site/www.zundert.nl/671859/"},
            "scoring": {"percentage": 81},
            "results": {
                "categories": {
                    "web_ipv6": {"verdict": "failed", "status": "failed"},
                    "web_dnssec": {"verdict": "passed", "status": "passed"},
                    "web_https": {"verdict": "unreachable", "status": "error"},
                    "web_appsecpriv": {"verdict": "warning", "status": "warning"},
                },
                "tests": {
                    "web_ipv6_ns_address": {"status": "passed", "verdict": "good"},
                    "web_ipv6_ns_reach": {"status": "passed", "verdict": "good"},
                    "web_ipv6_ws_address": {"status": "passed", "verdict": "good"},
                    "web_ipv6_ws_reach": {"status": "failed", "verdict": "bad"},
                    "web_ipv6_ws_similar": {"status": "not_tested", "verdict": "not-tested"},
                    "web_dnssec_exist": {"status": "passed", "verdict": "good"},
                    "web_dnssec_valid": {"status": "passed", "verdict": "good"},
                    "web_https_http_available": {"status": "error", "verdict": "other"},
                    "web_https_http_redirect": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_http_hsts": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_http_compress": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_keyexchange": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_ciphers": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_cipherorder": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_version": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_compress": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_secreneg": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_clientreneg": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_cert_chain": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_cert_pubkey": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_cert_sig": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_cert_domain": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_dane_exist": {"status": "info", "verdict": "bad"},
                    "web_https_dane_valid": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_0rtt": {"status": "not_tested", "verdict": "not-tested"},
                    "web_https_tls_ocsp": {"status": "info", "verdict": "ok"},
                    "web_https_tls_keyexchangehash": {"status": "not_tested", "verdict": "not-tested"},
                    "web_appsecpriv_x_frame_options": {"status": "not_tested", "verdict": "not-tested"},
                    "web_appsecpriv_referrer_policy": {"status": "not_tested", "verdict": "not-tested"},
                    "web_appsecpriv_csp": {"status": "not_tested", "verdict": "not-tested"},
                    "web_appsecpriv_x_content_type_options": {"status": "not_tested", "verdict": "not-tested"},
                },
                "custom": {"tls_1_3_support": "undetermined"},
            },
        },
    }

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/183
    # initialized in other method
    mail_results["dommel.nl"]["results"]["calculated_results"] = {}
    data = calculate_forum_standaardisatie_views_mail(mail_results["dommel.nl"])
    assert data["results"]["calculated_results"]["mail_legacy_dkim"]["status"] == "passed"

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/184

    assert "failed" == lowest_value_in_results(data, ["mail_ipv6_mx_address", "mail_ipv6_mx_reach"])

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/194
    # code delivered "passed", should be "not_tested", due to too low Lowest test outocome (5 instead of 10)
    assert "not_tested" == lowest_value_in_results(data, ["mail_auth_spf_policy"])

    add_calculation(
        scan_data=data,
        new_key="mail_legacy_ipv6_mailserver",
        required_values=["mail_ipv6_mx_address", "mail_ipv6_mx_reach"],
    )
    assert data["results"]["calculated_results"]["mail_legacy_ipv6_mailserver"]["status"] == "failed"

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/182
    mail_results["dommel2.nl"] = copy(mail_results["dommel.nl"])
    mail_results["dommel2.nl"]["results"]["custom"]["mail_non_sending_domain"] = False
    assert data["results"]["calculated_results"]["mail_legacy_mail_non_sending_domain"]["status"] == "info"
    assert data["results"]["calculated_results"]["mail_legacy_mail_sending_domain"]["status"] == "failed"
    data = calculate_forum_standaardisatie_views_mail(mail_results["dommel2.nl"])
    assert data["results"]["calculated_results"]["mail_legacy_mail_non_sending_domain"]["status"] == "not_applicable"
    assert data["results"]["calculated_results"]["mail_legacy_mail_sending_domain"]["status"] == "passed"

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/185
    # the test result gave "passed" while it was an error.
    mail_results["www.zundert.nl"]["results"]["calculated_results"] = {}
    data = calculate_forum_standaardisatie_views_web(mail_results["www.zundert.nl"])

    assert lowest_value_in_results(data, ["web_https_http_available"]) == "error"

    assert data["results"]["calculated_results"]["web_legacy_tls_available"]["status"] == "error"
