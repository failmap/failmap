from pathlib import Path
from datetime import datetime, timezone

import websecmap.reporting.time_cache
from websecmap.organizations.models import Url
from websecmap.scanners.models import (
    Endpoint,
    EndpointGenericScan,
    Scanner,
    ScannerFinding,
    Product,
    SecurityImpact,
)
from websecmap.scanners.scanner.nuclei_http import (
    convert_nuclei_data_to_json,
    extract_findings_to_scanner_findings,
    get_higher_severity,
    get_templates_from_scan_results,
    neutralize_missing_metrics,
    prepare_nuclei_results_for_storage,
    process_nuclei_record,
    split_nuclei_records_per_host,
    store_scan_batch,
    compose_verify_task,
    create_nuclei_scan_command,
    rate_nuclei_portal_finding,
    evidence_to_json,
    rerate_portal_findings,
    store_verify_results,
)

three_example_nuclei_tests = data = (
    b'{"template":"http/technologies/metatag-cms.yaml","template-url":"https://github.com/projectdiscovery/'
    b"nuclei-template"
    b's/blob/master/technologies/metatag-cms.yaml","template-id":"metatag-cms","template-path":"nuclei-'
    b'templates/technologies/metatag-cms.yaml","info":{"name":"Metatag CMS Detection","author":["dadevel"],"tags":["t'
    b'ech","cms"],"description":"Generic CMS Detection using html meta generator tag","reference":["https://www.w3sch'
    b'ools.com/tags/att_meta_name.asp"],"severity":"info"},"type":"http","host":"https://basisbeveiliging.nl","matche'
    b'd-at":"https://basisbeveiliging.nl","extracted-results":["Web Security Map by the Internet Cleanup Foundation"]'
    b',"ip":"185.71.61.127","timestamp":"2023-02-15T10:16:25.200938Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Ac'
    b"cept: */*' -H 'Accept-Language: en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWeb"
    b"Kit/537.36 (KHTML, like Gecko) Chrome/54.0.2866.71 Safari/537.36' 'https://basisbeveiliging.nl'\",\"matcher-st"
    b'atus":true,"matched-line":null}\n{"template":"http/technologies/tech-detect.yaml","template-url":'
    b'"https://github.com'
    b'/projectdiscovery/nuclei-templates/blob/master/technologies/tech-detect.yaml","template-id":"tech-detect","temp'
    b'late-path":"nuclei-templates/technologies/tech-detect.yaml","info":{"name":"Wappalyzer Technology'
    b' Detection","author":["hakluke"],"tags":["tech"],"reference":null,"severity":"info"},"matcher-name":"nginx","ty'
    b'pe":"http","host":"https://basisbeveiliging.nl","matched-at":"https://basisbeveiliging.nl","ip":"185.71.61.127"'
    b",\"timestamp\":\"2023-02-15T10:16:25.206073Z\",\"curl-command\":\"curl -X 'GET' -d '' -H 'Accept: */*' -H 'Acce"
    b"pt-Language: en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, li"
    b'ke Gecko) Chrome/54.0.2866.71 Safari/537.36\' \'https://basisbeveiliging.nl\'","matcher-status":true,"matched-l'
    b'ine":null}\n{"template":"http/technologies/waf-detect.yaml","template-url":"https://github.com/'
    b"projectdiscovery/nucl"
    b'ei-templates/blob/master/technologies/waf-detect.yaml","template-id":"waf-detect","template-path":"'
    b'nuclei-templates/technologies/waf-detect.yaml","info":{"name":"WAF Detection","author":["dwisiswant0","lu4nx"'
    b'],"tags":["waf","tech","misc"],"description":"A web application firewall was detected.","reference":["https://g'
    b'ithub.com/ekultek/whatwaf"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-n'
    b'ame":"nginxgeneric","type":"http","host":"https://basisbeveiliging.nl","matched-at":"https://basisbeveiliging.n'
    b'l/","ip":"185.71.61.127","timestamp":"2023-02-15T10:16:27.639418Z","curl-command":"curl -X \'POST\' -d \'_=\\u0'
    b"03cscript\\u003ealert(1)\\u003c/script\\u003e' -H 'Content-Type: application/x-www-form-urlencoded' -H 'Hos"
    b"t: basisbeveiliging.nl' -H 'User-Agent: Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like G"
    b'ecko) Chrome/41.0.2225.0 Safari/537.36\' \'https://basisbeveiliging.nl/\'","matcher-status":true,"matched-line"'
    b':null}\n{"template":"http/technologies/waf-detect.yaml","template-url":"https://github.com/projectdiscovery/nucl'
    b'ei-templates/blob/master/technologies/waf-detect.yaml","template-id":"waf-detect","template-path":"'
    b'nuclei-templates/technologies/waf-detect.yaml","info":{"name":"WAF Detection","author":["dwisiswant0","lu4nx"'
    b'],"tags":["waf","tech","misc"],"description":"A web application firewall was detected.","reference":["https://g'
    b'ithub.com/ekultek/whatwaf"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-n'
    b'ame":"nginxgeneric","type":"http","host":"https://basisbeveiliging2.nl","matched-at":"https://basisbeveiliging2.n'
    b'l/","ip":"185.71.61.127","timestamp":"2023-02-15T10:16:27.639418Z","curl-command":"curl -X \'POST\' -d \'_=\\u0'
    b"03cscript\\u003ealert(1)\\u003c/script\\u003e' -H 'Content-Type: application/x-www-form-urlencoded' -H 'Hos"
    b"t: basisbeveiliging2.nl' -H 'User-Agent: Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like G"
    b'ecko) Chrome/41.0.2225.0 Safari/537.36\' \'https://basisbeveiliging2.nl/\'","matcher-status":true,"matched-line"'
    b":null}\n"
)
# >>> [print(json.dumps(json.loads(line), indent=2)) for line in data.decode().strip().splitlines()]


def test_nuclei_store(db, current_path, reset_time_cache):
    url1 = Url.objects.create(**{"url": "basisbeveiliging.nl"})
    end1 = Endpoint.objects.create(**{"url": url1, "protocol": "https", "port": 443, "ip_version": 4})

    url2 = Url.objects.create(**{"url": "basisbeveiliging2.nl"})
    end2 = Endpoint.objects.create(**{"url": url2, "protocol": "https", "port": 443, "ip_version": 4})

    host_to_endpoint_mapping = {
        "https://basisbeveiliging.nl": {"endpoint": end1.id, "url": url1.id},
        "https://basisbeveiliging2.nl": {"endpoint": end2.id, "url": url2.id},
    }

    # no results should be no issue
    store_scan_batch(b"", host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 0

    # all categorized into the technologies area.
    store_scan_batch(three_example_nuclei_tests, host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 2

    # results are deduplicated
    store_scan_batch(three_example_nuclei_tests, host_to_endpoint_mapping)
    store_scan_batch(three_example_nuclei_tests, host_to_endpoint_mapping)
    store_scan_batch(three_example_nuclei_tests, host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 2


def test_split_metrics_per_host():
    # no records received:
    raw_nuclei_records = convert_nuclei_data_to_json(b"")
    assert len(raw_nuclei_records) == 0
    result = split_nuclei_records_per_host(raw_nuclei_records)
    assert len(result) == 0

    # some records received:
    raw_nuclei_records = convert_nuclei_data_to_json(three_example_nuclei_tests)
    result = split_nuclei_records_per_host(raw_nuclei_records)
    assert len(result["https://basisbeveiliging.nl"]) == 3
    assert len(result["https://basisbeveiliging2.nl"]) == 1

    for x, y in result.items():
        assert len(y) in [3, 1]


def test_convert_nuclei_data_to_json():
    data = convert_nuclei_data_to_json(three_example_nuclei_tests)
    assert data == [
        {
            "curl-command": "curl -X 'GET' -d '' -H 'Accept: */*' -H 'Accept-Language: "
            "en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X "
            "10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/54.0.2866.71 Safari/537.36' "
            "'https://basisbeveiliging.nl'",
            "extracted-results": ["Web Security Map by the Internet Cleanup Foundation"],
            "host": "https://basisbeveiliging.nl",
            "info": {
                "author": ["dadevel"],
                "description": "Generic CMS Detection using html meta generator tag",
                "name": "Metatag CMS Detection",
                "reference": ["https://www.w3schools.com/tags/att_meta_name.asp"],
                "severity": "info",
                "tags": ["tech", "cms"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging.nl",
            "matched-line": None,
            "matcher-status": True,
            "template": "http/technologies/metatag-cms.yaml",
            "template-id": "metatag-cms",
            "template-path": "nuclei-templates/technologies/metatag-cms.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/metatag-cms.yaml",
            "timestamp": "2023-02-15T10:16:25.200938Z",
            "type": "http",
        },
        {
            "curl-command": "curl -X 'GET' -d '' -H 'Accept: */*' -H 'Accept-Language: "
            "en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X "
            "10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/54.0.2866.71 Safari/537.36' "
            "'https://basisbeveiliging.nl'",
            "host": "https://basisbeveiliging.nl",
            "info": {
                "author": ["hakluke"],
                "name": "Wappalyzer Technology Detection",
                "reference": None,
                "severity": "info",
                "tags": ["tech"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging.nl",
            "matched-line": None,
            "matcher-name": "nginx",
            "matcher-status": True,
            "template": "http/technologies/tech-detect.yaml",
            "template-id": "tech-detect",
            "template-path": "nuclei-templates/technologies/tech-detect.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/tech-detect.yaml",
            "timestamp": "2023-02-15T10:16:25.206073Z",
            "type": "http",
        },
        {
            "curl-command": "curl -X 'POST' -d '_=<script>alert(1)</script>' -H "
            "'Content-Type: application/x-www-form-urlencoded' -H 'Host: "
            "basisbeveiliging.nl' -H 'User-Agent: Mozilla/5.0 (Windows "
            "NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/41.0.2225.0 Safari/537.36' "
            "'https://basisbeveiliging.nl/'",
            "host": "https://basisbeveiliging.nl",
            "info": {
                "author": ["dwisiswant0", "lu4nx"],
                "classification": {"cve-id": None, "cwe-id": ["cwe-200"]},
                "description": "A web application firewall was detected.",
                "name": "WAF Detection",
                "reference": ["https://github.com/ekultek/whatwaf"],
                "severity": "info",
                "tags": ["waf", "tech", "misc"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging.nl/",
            "matched-line": None,
            "matcher-name": "nginxgeneric",
            "matcher-status": True,
            "template": "http/technologies/waf-detect.yaml",
            "template-id": "waf-detect",
            "template-path": "nuclei-templates/technologies/waf-detect.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/waf-detect.yaml",
            "timestamp": "2023-02-15T10:16:27.639418Z",
            "type": "http",
        },
        {
            "curl-command": "curl -X 'POST' -d '_=<script>alert(1)</script>' -H "
            "'Content-Type: application/x-www-form-urlencoded' -H 'Host: "
            "basisbeveiliging2.nl' -H 'User-Agent: Mozilla/5.0 (Windows "
            "NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/41.0.2225.0 Safari/537.36' "
            "'https://basisbeveiliging2.nl/'",
            "host": "https://basisbeveiliging2.nl",
            "info": {
                "author": ["dwisiswant0", "lu4nx"],
                "classification": {"cve-id": None, "cwe-id": ["cwe-200"]},
                "description": "A web application firewall was detected.",
                "name": "WAF Detection",
                "reference": ["https://github.com/ekultek/whatwaf"],
                "severity": "info",
                "tags": ["waf", "tech", "misc"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging2.nl/",
            "matched-line": None,
            "matcher-name": "nginxgeneric",
            "matcher-status": True,
            "template": "http/technologies/waf-detect.yaml",
            "template-id": "waf-detect",
            "template-path": "nuclei-templates/technologies/waf-detect.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/waf-detect.yaml",
            "timestamp": "2023-02-15T10:16:27.639418Z",
            "type": "http",
        },
    ]


def test_process_nuclei_record():
    processed = process_nuclei_record(
        {
            # "curl-command": "curl -X 'POST' -d '_=<script>alert(1)</script>' -H "
            # "'Content-Type: application/x-www-form-urlencoded' -H 'Host: "
            # "basisbeveiliging.nl' -H 'User-Agent: Mozilla/5.0 (Windows "
            # "NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
            # "Chrome/41.0.2225.0 Safari/537.36' "
            # "'https://basisbeveiliging.nl/'",
            "host": "https://basisbeveiliging.nl",
            "info": {
                "author": ["dwisiswant0", "lu4nx"],
                "classification": {"cve-id": None, "cwe-id": ["cwe-200"]},
                "description": "A web application firewall was detected.",
                "name": "WAF Detection",
                "reference": ["https://github.com/ekultek/whatwaf"],
                "severity": "info",
                "tags": ["waf", "tech", "misc"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging.nl/",
            "matched-line": None,
            "matcher-name": "nginxgeneric",
            "matcher-status": True,
            "template": "http/technologies/waf-detect.yaml",
            "template-id": "waf-detect",
            "template-path": "nuclei-templates/technologies/waf-detect.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/waf-detect.yaml",
            "timestamp": "2023-02-15T10:16:27.639418Z",
            "type": "http",
        }
    )

    assert processed == {
        "category": "technologies",
        "evidence": {
            # "curl-command": "curl -X 'POST' -d '_=<script>alert(1)</script>' "
            # "-H 'Content-Type: "
            # "application/x-www-form-urlencoded' -H 'Host: "
            # "basisbeveiliging.nl' -H 'User-Agent: "
            # "Mozilla/5.0 (Windows NT 6.3; WOW64) "
            # "AppleWebKit/537.36 (KHTML, like Gecko) "
            # "Chrome/41.0.2225.0 Safari/537.36' "
            # "'https://basisbeveiliging.nl/'",
            "extracted-results": [],
            "matched-at": "https://basisbeveiliging.nl/",
        },
        "finding-name": "nuclei_waf_detect_nginxgeneric",
        "name": "WAF Detection",
        "severity": "info",
        "template-id": "waf-detect",
    }

    processed = process_nuclei_record(
        {
            # "curl-command": "curl -X 'GET' -d '' -H 'Accept: */*' -H 'Accept-Language: "
            # "en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X "
            # "10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) "
            # "Chrome/54.0.2866.71 Safari/537.36' "
            # "'https://basisbeveiliging.nl'",
            "host": "https://basisbeveiliging.nl",
            "info": {
                "author": ["hakluke"],
                "name": "Wappalyzer Technology Detection",
                "reference": None,
                "severity": "info",
                "tags": ["tech"],
            },
            "ip": "185.71.61.127",
            "matched-at": "https://basisbeveiliging.nl",
            "matched-line": None,
            "matcher-name": "nginx",
            "matcher-status": True,
            "template": "http/technologies/tech-detect.yaml",
            "template-id": "tech-detect",
            "template-path": "nuclei-templates/technologies/tech-detect.yaml",
            "template-url": "https://github.com/projectdiscovery/nuclei-templates/blob/master/"
            "technologies/tech-detect.yaml",
            "timestamp": "2023-02-15T10:16:25.206073Z",
            "type": "http",
        }
    )

    assert processed == {
        "category": "technologies",
        "evidence": {
            # "curl-command": "curl -X 'GET' -d '' -H 'Accept: */*' -H "
            # "'Accept-Language: en' -H 'User-Agent: "
            # "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) "
            # "AppleWebKit/537.36 (KHTML, like Gecko) "
            # "Chrome/54.0.2866.71 Safari/537.36' "
            # "'https://basisbeveiliging.nl'",
            "extracted-results": [],
            "matched-at": "https://basisbeveiliging.nl",
        },
        "finding-name": "nuclei_tech_detect_nginx",
        "name": "Wappalyzer Technology Detection",
        "severity": "info",
        "template-id": "tech-detect",
    }

    assert process_nuclei_record({}) == {
        "category": "unknown",
        "evidence": {"extracted-results": [], "matched-at": ""},
        "finding-name": "nuclei_unknown",
        "name": "unknown",
        "severity": "unknown",
        "template-id": "unknown",
    }


def test_categorize_nuclei_record(db):
    """Correct category for template should be fetched from records in
    output (after nuclie added subcategories (eg: http, dns, etc)"""

    nuclei_data = open(Path(__file__).parent / "nuclei_output.bin", "rb").read()

    assert nuclei_data

    raw_nuclei_records = convert_nuclei_data_to_json(nuclei_data)
    output = prepare_nuclei_results_for_storage(raw_nuclei_records)
    assert sorted(output.keys()) == [
        "nuclei_dns",
        "nuclei_exposed_panels",
        "nuclei_exposures",
        "nuclei_miscellaneous",
        "nuclei_ssl",
        "nuclei_technologies",
    ]


def test_categorize_nuclei_record_old_templates(db):
    """Correct category for template should be fetched from records in output (before nuclie added subcategories"""

    data = open(Path(__file__).parent / "nuclei_output_old.bin", "rb").read()

    raw_nuclei_records = convert_nuclei_data_to_json(data)
    output = prepare_nuclei_results_for_storage(raw_nuclei_records)
    assert sorted(output.keys()) == [
        "nuclei_exposed_panels",
        "nuclei_exposures",
        "nuclei_miscellaneous",
        "nuclei_technologies",
    ]

    assert output["nuclei_exposed_panels"] == {
        "amount-of-findings": 2,
        "findings": [
            {
                "evidence": {
                    # "curl-command": "curl -X 'GET' "
                    # "-d '' -H "
                    # "'Accept: */*' "
                    # "-H "
                    # "'Accept-Language: "
                    # "en' -H "
                    # "'User-Agent: "
                    # "Mozilla/5.0 "
                    # "(Windows NT "
                    # "6.1; WOW64) "
                    # "AppleWebKit/537.36 "
                    # "(KHTML, like "
                    # "Gecko) "
                    # "Chrome/36.0.1985.67 "
                    # "Safari/537.36' "
                    # "'https://www.example.com'",
                    "extracted-results": [],
                    "matched-at": "https://www.example.com",
                },
                "finding-name": "nuclei_drupal_login",
                "name": "Drupal Login Panel - Detect",
                "template-id": "drupal-login",
            },
            {
                "evidence": {
                    # "curl-command": "curl -X 'GET' "
                    # "-d '' -H "
                    # "'Accept: */*' "
                    # "-H "
                    # "'Accept-Language: "
                    # "en' -H "
                    # "'User-Agent: "
                    # "Mozilla/5.0 "
                    # "(Windows NT "
                    # "10.0; Win64; "
                    # "x64) "
                    # "AppleWebKit/537.36 "
                    # "(KHTML, like "
                    # "Gecko) "
                    # "Chrome/70.0.3538.77 "
                    # "Safari/537.36' "
                    # "'https://www.example.com/phpmyadmin/'",
                    "extracted-results": ["4.9.0.1"],
                    "matched-at": "https://www.example.com/phpmyadmin/",
                },
                "finding-name": "nuclei_phpmyadmin_panel",
                "name": "phpMyAdmin Panel - Detect",
                "template-id": "phpmyadmin-panel",
            },
        ],
        "highest-severity": "info",
    }


def test_get_higher_severity():
    assert get_higher_severity("high", "info") == "high"
    assert get_higher_severity("low", "high") == "high"
    assert get_higher_severity("low", "low") == "low"


def test_neutralize_missing_metrics(db):
    url = Url.objects.create(**{"url": "example.com"})
    endpoint = Endpoint.objects.create(**{"url": url})

    # nothing happens, nothing in the database at all...
    neutralize_missing_metrics(["nuclei_exposed_panels"], endpoint.id)

    # add two new metrics, in different categories. One of them is in the result, the other isn't...
    default = {"endpoint": endpoint, "is_the_latest_scan": True, "rating_determined_on": datetime.now(timezone.utc)}
    EndpointGenericScan.objects.create(type="nuclei_exposed_panels", rating="high", **default)
    EndpointGenericScan.objects.create(type="nuclei_exposures", rating="high", **default)
    assert EndpointGenericScan.objects.count() == 2
    # For the missing one, a "clean" result is added once:
    neutralize_missing_metrics(["nuclei_exposed_panels"], endpoint.id)
    neutralize_missing_metrics(["nuclei_exposed_panels"], endpoint.id)
    neutralize_missing_metrics(["nuclei_exposed_panels"], endpoint.id)
    assert EndpointGenericScan.objects.count() == 3

    # now remove both results:
    neutralize_missing_metrics([], endpoint.id)
    assert EndpointGenericScan.objects.count() == 4

    # Check that they are really clean:
    assert EndpointGenericScan.objects.get(type="nuclei_exposed_panels", is_the_latest_scan=True).rating == "clean"


CITRIX_SCAN_RESULTS = """[
    {"name": "Citrix VPN Panel - Detect", "finding-name": "nuclei_citrix_vpn_detect",
     "template-id": "citrix-vpn-panel",
     "evidence": {"extracted-results": [], "matched-at": "https:///vpn/index.html"}},
    {"name": "NetScaler AAA Login Panel - Detect", "finding-name": "nuclei_netscaler_aaa_login",
     "template-id": "netscaler-aaa-login-panel",
     "evidence": {"extracted-results": [],
                  "matched-at": "https:///LogonPoint/tmindex.html"}}]"""


def test_rate_nuclei_portal_finding(db, default_scan_metadata, reset_time_cache):
    # monkey patch it, perhaps reset_time_cache does not work... which is the case...
    websecmap.reporting.time_cache.CACHE = {}

    # nothing in the database, so an 'ok' rating which is the default
    rating = rate_nuclei_portal_finding(evidence_to_json(CITRIX_SCAN_RESULTS))
    assert rating == "ok"

    # now add the product to the database, map it to this template and set it to high impact
    sf = ScannerFinding()
    sf.name = "nuclei_citrix_vpn_detect"
    sf.scanner = Scanner.objects.get(name="nuclei_http")
    sf.save()

    sf2 = ScannerFinding()
    sf2.name = "nuclei_netscaler_aaa_login"
    sf2.scanner = Scanner.objects.get(name="nuclei_http")
    sf2.save()

    si = SecurityImpact.objects.create(**{"name": "high"})
    si2 = SecurityImpact.objects.create(**{"name": "medium"})

    prod = Product.objects.create(**{"name": "Citrix VPN"})
    prod.login_panel_presence_security_impact = si
    prod.scanner_finding_name_mapping.add(sf)
    prod.save()

    prod2 = Product.objects.create(**{"name": "Netscaler"})
    prod2.login_panel_presence_security_impact = si2
    prod2.scanner_finding_name_mapping.add(sf2)
    prod2.save()

    # make sure it's high, not medium. Both panels are present.
    rating = rate_nuclei_portal_finding(evidence_to_json(CITRIX_SCAN_RESULTS))
    assert rating == "high"

    # add an endpointgeneric scan with a low rating and rerate.
    url = Url.objects.create(**{"url": "example.com"})
    endpoint = Endpoint.objects.create(**{"url": url, "protocol": "http"})
    EndpointGenericScan.objects.create(
        type="nuclei_exposed_panels",
        rating="low",
        evidence=CITRIX_SCAN_RESULTS,
        endpoint=endpoint,
        is_the_latest_scan=True,
        rating_determined_on=datetime.now(timezone.utc),
    )

    rerate_portal_findings()

    # first one, so a 'get' will work :)
    assert EndpointGenericScan.objects.get(type="nuclei_exposed_panels", is_the_latest_scan=True).rating == "high"

    assert EndpointGenericScan.objects.get(type="nuclei_exposed_panels", is_the_latest_scan=True).meaning == {
        "tech": [
            {
                "portal_extracted": [],
                "portal_name": "Citrix VPN Panel",
                "portal_url": "https:///vpn/index.html",
                "tech": [{"product": prod.id, "version": "unknown"}, {"product": prod2.id, "version": "unknown"}],
            },
            {
                "portal_extracted": [],
                "portal_name": "NetScaler AAA Login Panel",
                "portal_url": "https:///LogonPoint/tmindex.html",
                "tech": [{"product": prod2.id, "version": "unknown"}, {"product": prod.id, "version": "unknown"}],
            },
        ]
    }

    # verification delivers the same stuff, with the same rating and tech
    store_verify_results(three_example_nuclei_tests, endpoint.id, "nuclei_exposed_panels")
    assert EndpointGenericScan.objects.filter(type="nuclei_exposed_panels").count() == 2

    # so what has changed? -> the evidence is not stored in above tests...
    first = EndpointGenericScan.objects.filter(type="nuclei_exposed_panels").first()
    last = EndpointGenericScan.objects.filter(type="nuclei_exposed_panels").last()

    assert first.id != last.id
    assert first.evidence != last.evidence
    assert evidence_to_json(last.evidence) == evidence_to_json(CITRIX_SCAN_RESULTS)


def test_get_templates_from_scan_results(db):
    assert list(sorted(get_templates_from_scan_results(evidence_to_json(CITRIX_SCAN_RESULTS)))) == list(
        sorted(["citrix-vpn-panel", "netscaler-aaa-login-panel"])
    )

    assert get_templates_from_scan_results(evidence_to_json("""[]""")) == []


def test_extract_findings_to_scanner_findings(db, default_scan_metadata):
    url = Url.objects.create(**{"url": "example.com"})
    endpoint = Endpoint.objects.create(**{"url": url, "protocol": "http", "port": 443})
    EndpointGenericScan.objects.create(
        type="nuclei_exposed_panels",
        rating="info",
        evidence=CITRIX_SCAN_RESULTS,
        endpoint=endpoint,
        is_the_latest_scan=True,
        rating_determined_on=datetime.now(timezone.utc),
    )

    extract_findings_to_scanner_findings()

    assert ScannerFinding.objects.all().count() == 2


def create_sample_data_for_url(url_str: str, scan_type: str, scan_data=None):
    url, _ = Url.objects.get_or_create(**{"url": url_str})
    endpoint, _ = Endpoint.objects.get_or_create(**{"url": url, "protocol": "http", "port": 443})
    EndpointGenericScan.objects.create(
        type=scan_type,
        rating="info",
        evidence=scan_data,
        endpoint=endpoint,
        is_the_latest_scan=True,
        rating_determined_on=datetime.now(timezone.utc),
    )
    return url


def test_nuclei_compose_verify_task(db):
    # should create 2 scans on this domain, one for each prior scan:
    create_sample_data_for_url(
        "mail.rhcvechtenvenen.nl",
        "nuclei_exposed_panels",
        """[
        {"template-id": "phpmyadmin-panel", "name": "phpMyAdmin Panel - Detect", "finding-name": "nuclei_phpmyadmin_panel", "evidence": {"extracted-results": ["5.2.1"], "matched-at": "https://mail.rhcvechtenvenen.nl:443/phpmyadmin/"}}
    ]""",  # noqa
    )
    create_sample_data_for_url(
        "mail.rhcvechtenvenen.nl",
        "nuclei_technologies",
        """[
        {"template-id": "apache-detect", "name": "Apache Detection", "finding-name": "nuclei_apache_detect", "evidence": {"extracted-results": ["Apache/2"], "matched-at": "https://mail.rhcvechtenvenen.nl:443"}},
        {"template-id": "waf-detect", "name": "WAF Detection", "finding-name": "nuclei_waf_detect_apachegeneric", "evidence": {"extracted-results": [], "matched-at": "https://mail.rhcvechtenvenen.nl:443/"}}]
        """,  # noqa
    )

    create_sample_data_for_url(
        "tw.omnibuzz.nl",
        "nuclei_technologies",
        """[
        {"template-id": "apache-detect", "name": "Apache Detection", "finding-name": "nuclei_apache_detect", "evidence": {"extracted-results": ["Apache"], "matched-at": "https://tw.omnibuzz.nl:443"}},
        {"template-id": "favicon-detect", "name": "favicon-detection", "finding-name": "nuclei_favicon_detect_mitel_networks_micollab_end_user_portal", "evidence": {"extracted-results": [], "matched-at": "https://tw.omnibuzz.nl:443/favicon.ico"}},
        {"template-id": "waf-detect", "name": "WAF Detection", "finding-name": "nuclei_waf_detect_apachegeneric", "evidence": {"extracted-results": [], "matched-at": "https://tw.omnibuzz.nl:443/"}}]
        """,  # noqa
    )
    create_sample_data_for_url(
        "erfgoed.utrecht.nl",
        "nuclei_technologies",
        """[
        {"template-id": "metatag-cms", "name": "Metatag CMS Detection", "finding-name": "nuclei_metatag_cms", "evidence": {"extracted-results": ["TYPO3 CMS"], "matched-at": "https://erfgoed.utrecht.nl:443"}},
        {"template-id": "tech-detect", "name": "Wappalyzer Technology Detection", "finding-name": "nuclei_tech_detect_typo3_cms", "evidence": {"extracted-results": [], "matched-at": "https://erfgoed.utrecht.nl:443"}},
        {"template-id": "typo3-detect", "name": "TYPO3 Detection", "finding-name": "nuclei_typo3_detect", "evidence": {"extracted-results": [], "matched-at": "https://erfgoed.utrecht.nl:443"}}]
    """,  # noqa
    )
    create_sample_data_for_url(
        "serviscope-acc.kpn.com",
        "nuclei_technologies",
        """[
        {"template-id": "tech-detect", "name": "Wappalyzer Technology Detection", "finding-name": "nuclei_tech_detect_awselb", "evidence": {"extracted-results": [], "matched-at": "https://serviscope-acc.kpn.com:443"}}]
    """,  # noqa
    )

    task = list(
        compose_verify_task(
            {},
            {"args": []},
        )
    )

    assert len(task) == 5

    # check that 'args' is set correctly, so only the right template id's are used in verification, otherwise all
    # scans will be performed on all levels
    assert (
        str(task[0]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://mail.rhcvechtenvenen.nl:443', {'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['phpmyadmin-panel']}]})"  # noqa
    )
    assert (
        str(task[1]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://mail.rhcvechtenvenen.nl:443', {'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['apache-detect', 'waf-detect']}]})"  # noqa
    )
    assert (
        str(task[2]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://tw.omnibuzz.nl:443', {'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['apache-detect', 'favicon-detect', 'waf-detect']}]})"  # noqa
    )
    assert (
        str(task[3]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://erfgoed.utrecht.nl:443', {'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['metatag-cms', 'tech-detect', 'typo3-detect']}]})"  # noqa
    )
    assert (
        str(task[4]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://serviscope-acc.kpn.com:443', {'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['tech-detect']}]})"  # noqa
    )

    # see if args are merged correctly, which is usual for normal verification:
    # this includes headers, template tags and such.
    task = list(
        compose_verify_task(
            {},
            {},
        )
    )

    assert (
        str(task[0]["kwargs"]["tasks"][0])
        == "websecmap.scanners.scanner.nuclei_http.scan('http://mail.rhcvechtenvenen.nl:443', {'args': ["
           "{'name': 'silent', 'type': 'no-value'}, {'name': 'disable-update-check', 'type': 'no-value'}, "
           "{'name': 'disable-unsigned-templates', 'type': 'no-value'}, "
           "{'name': 'rate-limit', 'type': 'single-argument', 'value': '10'}, "
           "{'name': 'config-directory', 'type': 'single-argument', 'value': '/tmp'}, "
           "{'name': 'tags', 'type': 'list-to-duplicate-arguments', 'value': ['panel', 'tech']}, "
           "{'name': 'header', 'type': 'single-argument', 'value': \"'User-Agent: Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.62 Mobile Safari/537.36 (compatible; ICF-Basisbeveiliging/1.0; +https://internetcleanup.foundation/scaninfo)'\"}, "  # noqa
           "{'name': 'template-id', 'type': 'list-to-duplicate-arguments', 'value': ['phpmyadmin-panel']}"
           "], 'amount': 25})"  # noqa
    )


def test_create_nuclei_scan_command(db):
    command = create_nuclei_scan_command(
        ["test.nl"],
        "/usr/local/bin/nuclei",
        {
            "args": [
                {"name": "silent", "type": "no-value"},
                {"name": "disable-update-check", "type": "no-value"},
                {"name": "rate-limit", "type": "single-argument", "value": "10"},
                {"name": "config-directory", "type": "single-argument", "value": "/tmp"},
                {
                    "name": "template-id",
                    "type": "list-to-duplicate-arguments",
                    "value": ["netscaler-aaa-login-panel", "citrix-vpn-panel"],
                },
            ]
        },
        disabled_templates=["robots-txt", "security-txt"],
    )
    assert command == [
        "/usr/local/bin/nuclei",
        "-jsonl",
        "-silent",
        "-disable-update-check",
        "-rate-limit",
        "10",
        "-config-directory",
        "/tmp",
        "-template-id",
        "netscaler-aaa-login-panel",
        "-template-id",
        "citrix-vpn-panel",
        "-exclude-id",
        "robots-txt,security-txt",
        "-target",
        "test.nl",
    ]
