from datetime import datetime, timezone

from websecmap.app import log
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, PlannedScan, Scanner, ScannerFinding
from websecmap.scanners.scanner.nuclei_http import (
    compose_planned_verify_task,
    convert_nuclei_data_to_json,
    extract_findings_to_scanner_findings,
    get_higher_severity,
    get_templates_from_scan_results,
    neutralize_missing_metrics,
    plan_verify,
    prepare_nuclei_results_for_storage,
    process_nuclei_record,
    split_nuclei_records_per_host,
    store_new_scan_results,
    compose_verify_task,
    create_nuclei_scan_command,
)
from constance.test import override_config

three_example_nuclei_tests = data = (
    b'{"template":"technologies/metatag-cms.yaml","template-url":"https://github.com/projectdiscovery/nuclei-template'
    b's/blob/master/technologies/metatag-cms.yaml","template-id":"metatag-cms","template-path":"nuclei-'
    b'templates/technologies/metatag-cms.yaml","info":{"name":"Metatag CMS Detection","author":["dadevel"],"tags":["t'
    b'ech","cms"],"description":"Generic CMS Detection using html meta generator tag","reference":["https://www.w3sch'
    b'ools.com/tags/att_meta_name.asp"],"severity":"info"},"type":"http","host":"https://basisbeveiliging.nl","matche'
    b'd-at":"https://basisbeveiliging.nl","extracted-results":["Web Security Map by the Internet Cleanup Foundation"]'
    b',"ip":"185.71.61.127","timestamp":"2023-02-15T10:16:25.200938Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Ac'
    b"cept: */*' -H 'Accept-Language: en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWeb"
    b"Kit/537.36 (KHTML, like Gecko) Chrome/54.0.2866.71 Safari/537.36' 'https://basisbeveiliging.nl'\",\"matcher-st"
    b'atus":true,"matched-line":null}\n{"template":"technologies/tech-detect.yaml","template-url":"https://github.com'
    b'/projectdiscovery/nuclei-templates/blob/master/technologies/tech-detect.yaml","template-id":"tech-detect","temp'
    b'late-path":"nuclei-templates/technologies/tech-detect.yaml","info":{"name":"Wappalyzer Technology'
    b' Detection","author":["hakluke"],"tags":["tech"],"reference":null,"severity":"info"},"matcher-name":"nginx","ty'
    b'pe":"http","host":"https://basisbeveiliging.nl","matched-at":"https://basisbeveiliging.nl","ip":"185.71.61.127"'
    b",\"timestamp\":\"2023-02-15T10:16:25.206073Z\",\"curl-command\":\"curl -X 'GET' -d '' -H 'Accept: */*' -H 'Acce"
    b"pt-Language: en' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, li"
    b'ke Gecko) Chrome/54.0.2866.71 Safari/537.36\' \'https://basisbeveiliging.nl\'","matcher-status":true,"matched-l'
    b'ine":null}\n{"template":"technologies/waf-detect.yaml","template-url":"https://github.com/projectdiscovery/nucl'
    b'ei-templates/blob/master/technologies/waf-detect.yaml","template-id":"waf-detect","template-path":"'
    b'nuclei-templates/technologies/waf-detect.yaml","info":{"name":"WAF Detection","author":["dwisiswant0","lu4nx"'
    b'],"tags":["waf","tech","misc"],"description":"A web application firewall was detected.","reference":["https://g'
    b'ithub.com/ekultek/whatwaf"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-n'
    b'ame":"nginxgeneric","type":"http","host":"https://basisbeveiliging.nl","matched-at":"https://basisbeveiliging.n'
    b'l/","ip":"185.71.61.127","timestamp":"2023-02-15T10:16:27.639418Z","curl-command":"curl -X \'POST\' -d \'_=\\u0'
    b"03cscript\\u003ealert(1)\\u003c/script\\u003e' -H 'Content-Type: application/x-www-form-urlencoded' -H 'Hos"
    b"t: basisbeveiliging.nl' -H 'User-Agent: Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like G"
    b'ecko) Chrome/41.0.2225.0 Safari/537.36\' \'https://basisbeveiliging.nl/\'","matcher-status":true,"matched-line"'
    b':null}\n{"template":"technologies/waf-detect.yaml","template-url":"https://github.com/projectdiscovery/nucl'
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


def test_nuclei_store(db, current_path):
    url1 = Url.objects.create(**{"url": "basisbeveiliging.nl"})
    end1 = Endpoint.objects.create(**{"url": url1, "protocol": "https", "port": 443, "ip_version": 4})

    url2 = Url.objects.create(**{"url": "basisbeveiliging2.nl"})
    end2 = Endpoint.objects.create(**{"url": url2, "protocol": "https", "port": 443, "ip_version": 4})

    host_to_endpoint_mapping = {
        "https://basisbeveiliging.nl": {"endpoint": end1.id, "url": url1.id},
        "https://basisbeveiliging2.nl": {"endpoint": end2.id, "url": url2.id},
    }

    # no results should be no issue
    store_new_scan_results(b"", host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 0

    # all categorized into the technologies area.
    store_new_scan_results(three_example_nuclei_tests, host_to_endpoint_mapping)
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
            "template": "technologies/metatag-cms.yaml",
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
            "template": "technologies/tech-detect.yaml",
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
            "template": "technologies/waf-detect.yaml",
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
            "template": "technologies/waf-detect.yaml",
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
            "template": "technologies/waf-detect.yaml",
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
            "template": "technologies/tech-detect.yaml",
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


def test_categorize_nuclei_record():
    data = b"""{"template":"technologies/apache/apache-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/apache/apache-detect.yaml","template-id":"apache-detect","template-path":"nuclei-templates/technologies/apache/apache-detect.yaml","info":{"name":"Apache Detection","author":["philippedelteil"],"tags":["tech","apache"],"description":"Some Apache servers have the version on the response header. The OpenSSL version can be also obtained","reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","extracted-results":["Apache"],"ip":"141.94.18.147","timestamp":"2023-02-15T12:05:51.027829Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2919.83 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/google-floc-disabled.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/google-floc-disabled.yaml","template-id":"google-floc-disabled","template-path":"nuclei-templates/miscellaneous/google-floc-disabled.yaml","info":{"name":"Google FLoC Disabled","author":["geeknik"],"tags":["google","floc","misc"],"description":"The detected website has decided to explicitly exclude itself from Google FLoC tracking.","reference":["https://www.bleepingcomputer.com/news/security/github-disables-google-floc-user-tracking-on-its-website/"],"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:05:51.152216Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2919.83 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/tech-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/tech-detect.yaml","template-id":"tech-detect","template-path":"nuclei-templates/technologies/tech-detect.yaml","info":{"name":"Wappalyzer Technology Detection","author":["hakluke"],"tags":["tech"],"reference":null,"severity":"info"},"matcher-name":"jsdelivr","type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:05:52.893625Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/tech-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/tech-detect.yaml","template-id":"tech-detect","template-path":"nuclei-templates/technologies/tech-detect.yaml","info":{"name":"Wappalyzer Technology Detection","author":["hakluke"],"tags":["tech"],"reference":null,"severity":"info"},"matcher-name":"drupal","type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:05:52.893652Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/metatag-cms.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/metatag-cms.yaml","template-id":"metatag-cms","template-path":"nuclei-templates/technologies/metatag-cms.yaml","info":{"name":"Metatag CMS Detection","author":["dadevel"],"tags":["tech","cms"],"description":"Generic CMS Detection using html meta generator tag","reference":["https://www.w3schools.com/tags/att_meta_name.asp"],"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","extracted-results":["Drupal 9 (https://www.drupal.org)"],"ip":"141.94.18.147","timestamp":"2023-02-15T12:05:52.895156Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/fingerprinthub-web-fingerprints.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/fingerprinthub-web-fingerprints.yaml","template-id":"fingerprinthub-web-fingerprints","template-path":"nuclei-templates/technologies/fingerprinthub-web-fingerprints.yaml","info":{"name":"FingerprintHub Technology Fingerprint","author":["pdteam","righettod"],"tags":["tech"],"description":"FingerprintHub Technology Fingerprint tests run in nuclei.","reference":["https://github.com/0x727/fingerprinthub"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-name":"drupal","type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:05:52.977542Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/drupal-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/drupal-detect.yaml","template-id":"drupal-detect","template-path":"nuclei-templates/technologies/drupal-detect.yaml","info":{"name":"Drupal Detection","author":["1nf1n7y"],"tags":["tech","drupal"],"reference":null,"severity":"info","metadata":{"verified":true,"shodan-query":"http.component:\\"Drupal\\""}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:05:54.641767Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.137 Safari/4E423F\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/options-method.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/options-method.yaml","template-id":"options-method","template-path":"nuclei-templates/miscellaneous/options-method.yaml","info":{"name":"Allowed Options Method","author":["pdteam"],"tags":["misc","generic"],"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","extracted-results":["GET, POST"],"ip":"141.94.18.147","timestamp":"2023-02-15T12:05:56.124195Z","curl-command":"curl -X \'OPTIONS\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2117.157 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"exposures/files/readme-md.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/exposures/files/readme-md.yaml","template-id":"readme-md","template-path":"nuclei-templates/exposures/files/readme-md.yaml","info":{"name":"README.md file disclosure","author":["ambassify"],"tags":["exposure","markdown","files"],"description":"Internal documentation file often used in projects which can contain sensitive information.","reference":null,"severity":"info","metadata":{"shodan-query":"html:\\"README.MD\\""}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/README.md","ip":"141.94.18.147","timestamp":"2023-02-15T12:06:11.304687Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36\' \'https://www.example.com/README.md\'","matcher-status":true,"matched-line":null}\n{"template":"exposures/files/build-properties.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/exposures/files/build-properties.yaml","template-id":"build-properties","template-path":"nuclei-templates/exposures/files/build-properties.yaml","info":{"name":"Build Properties File Exposure","author":["dhiyaneshdk"],"tags":["exposure","config","files"],"reference":null,"severity":"info","metadata":{"verified":true,"google-query":"intitle:\\"index of\\" \\"build.properties\\""}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/manual/style/build.properties","ip":"141.94.18.147","timestamp":"2023-02-15T12:06:44.177451Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux i686 on x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2820.59 Safari/537.36\' \'https://www.example.com/manual/style/build.properties\'","matcher-status":true,"matched-line":null}\n{"template":"exposed-panels/drupal-login.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/exposed-panels/drupal-login.yaml","template-id":"drupal-login","template-path":"nuclei-templates/exposed-panels/drupal-login.yaml","info":{"name":"Drupal Login Panel - Detect","author":["pathtaga"],"tags":["panel","drupal"],"description":"Drupal login panel was detected.","reference":null,"severity":"info","metadata":{"shodan-query":"http.component:\\"drupal\\""},"classification":{"cve-id":null,"cwe-id":["cwe-200"],"cvss-metrics":"CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N"}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com","ip":"141.94.18.147","timestamp":"2023-02-15T12:06:44.895881Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36\' \'https://www.example.com\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/robots.txt","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:06.406361Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2224.3 Safari/537.36\' \'https://www.example.com/robots.txt\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/README.txt","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:06.496345Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36\' \'https://www.example.com/README.txt\'","matcher-status":true,"matched-line":null}\n{"template":"exposed-panels/phpmyadmin-panel.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/exposed-panels/phpmyadmin-panel.yaml","template-id":"phpmyadmin-panel","template-path":"nuclei-templates/exposed-panels/phpmyadmin-panel.yaml","info":{"name":"phpMyAdmin Panel - Detect","author":["pdteam"],"tags":["panel","phpmyadmin"],"description":"phpMyAdmin panel was detected.","reference":null,"severity":"info","metadata":{"shodan-query":"http.title:phpMyAdmin"},"classification":{"cve-id":null,"cwe-id":["cwe-200"],"cvss-metrics":"CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N"}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/phpmyadmin/","extracted-results":["4.9.0.1"],"ip":"141.94.18.147","timestamp":"2023-02-15T12:07:09.16058Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36\' \'https://www.example.com/phpmyadmin/\'","matcher-status":true,"matched-line":null}\n{"template":"exposures/configs/netbeans-config.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/exposures/configs/netbeans-config.yaml","template-id":"netbeans-config","template-path":"nuclei-templates/exposures/configs/netbeans-config.yaml","info":{"name":"Netbeans Config - Detect","author":["sbani"],"tags":["netbeans","config","exposure"],"description":"Netbeans configuration information was detected.","reference":["https://netbeans.apache.org/"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"],"cvss-metrics":"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N","cvss-score":5.3}},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/nbproject/project.properties","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:13.727075Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36\' \'https://www.example.com/nbproject/project.properties\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/waf-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/waf-detect.yaml","template-id":"waf-detect","template-path":"nuclei-templates/technologies/waf-detect.yaml","info":{"name":"WAF Detection","author":["dwisiswant0","lu4nx"],"tags":["waf","tech","misc"],"description":"A web application firewall was detected.","reference":["https://github.com/ekultek/whatwaf"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-name":"ats","type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:30.73564Z","curl-command":"curl -X \'POST\' -d \'_=\\u003cscript\\u003ealert(1)\\u003c/script\\u003e\' -H \'Content-Type: application/x-www-form-urlencoded\' -H \'Host: www.example.com\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36\' \'https://www.example.com/\'","matcher-status":true,"matched-line":null}\n{"template":"technologies/waf-detect.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/waf-detect.yaml","template-id":"waf-detect","template-path":"nuclei-templates/technologies/waf-detect.yaml","info":{"name":"WAF Detection","author":["dwisiswant0","lu4nx"],"tags":["waf","tech","misc"],"description":"A web application firewall was detected.","reference":["https://github.com/ekultek/whatwaf"],"severity":"info","classification":{"cve-id":null,"cwe-id":["cwe-200"]}},"matcher-name":"apachegeneric","type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:30.735673Z","curl-command":"curl -X \'POST\' -d \'_=\\u003cscript\\u003ealert(1)\\u003c/script\\u003e\' -H \'Content-Type: application/x-www-form-urlencoded\' -H \'Host: www.example.com\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36\' \'https://www.example.com/\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/user/password","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:32.752848Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36\' \'https://www.example.com/user/password\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/user/register","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:43.239553Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.137 Safari/4E423F\' \'https://www.example.com/user/register\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/user/login","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:52.299194Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML like Gecko) Chrome/44.0.2403.155 Safari/537.36\' \'https://www.example.com/user/login\'","matcher-status":true,"matched-line":null}\n{"template":"miscellaneous/robots-txt-endpoint.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/miscellaneous/robots-txt-endpoint.yaml","template-id":"robots-txt-endpoint","template-path":"nuclei-templates/miscellaneous/robots-txt-endpoint.yaml","info":{"name":"robots.txt endpoint prober","author":["caspergn","pdteam"],"tags":null,"reference":null,"severity":"info"},"type":"http","host":"https://www.example.com","matched-at":"https://www.example.com/filter/tips","ip":"141.94.18.147","timestamp":"2023-02-15T12:07:57.112393Z","curl-command":"curl -X \'GET\' -d \'\' -H \'Accept: */*\' -H \'Accept-Language: en\' -H \'User-Agent: Mozilla/5.0 (X11; Ubuntu; Linux i686 on x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2820.59 Safari/537.36\' \'https://www.example.com/filter/tips\'","matcher-status":true,"matched-line":null}\n"""  # noqa

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


def test_get_templates_from_scan_results():
    assert list(sorted(get_templates_from_scan_results(CITRIX_SCAN_RESULTS))) == list(
        sorted(["citrix-vpn-panel", "netscaler-aaa-login-panel"])
    )

    assert get_templates_from_scan_results("""[]""") == []


def test_nuclei_plan_verify(db, default_scan_metadata):
    Scanner.objects.create(**{"name": "nuclei_http", "python_name": "nuclei_http"})

    plan_verify()
    assert PlannedScan.objects.count() == 0

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

    plan_verify()

    assert PlannedScan.objects.count() == 1

    verify_task = compose_planned_verify_task()
    assert verify_task is not None


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
    url1 = create_sample_data_for_url(
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

    url2 = create_sample_data_for_url(
        "tw.omnibuzz.nl",
        "nuclei_technologies",
        """[
        {"template-id": "apache-detect", "name": "Apache Detection", "finding-name": "nuclei_apache_detect", "evidence": {"extracted-results": ["Apache"], "matched-at": "https://tw.omnibuzz.nl:443"}}, 
        {"template-id": "favicon-detect", "name": "favicon-detection", "finding-name": "nuclei_favicon_detect_mitel_networks_micollab_end_user_portal", "evidence": {"extracted-results": [], "matched-at": "https://tw.omnibuzz.nl:443/favicon.ico"}}, 
        {"template-id": "waf-detect", "name": "WAF Detection", "finding-name": "nuclei_waf_detect_apachegeneric", "evidence": {"extracted-results": [], "matched-at": "https://tw.omnibuzz.nl:443/"}}]
        """,  # noqa
    )
    url3 = create_sample_data_for_url(
        "erfgoed.utrecht.nl",
        "nuclei_technologies",
        """[
        {"template-id": "metatag-cms", "name": "Metatag CMS Detection", "finding-name": "nuclei_metatag_cms", "evidence": {"extracted-results": ["TYPO3 CMS"], "matched-at": "https://erfgoed.utrecht.nl:443"}}, 
        {"template-id": "tech-detect", "name": "Wappalyzer Technology Detection", "finding-name": "nuclei_tech_detect_typo3_cms", "evidence": {"extracted-results": [], "matched-at": "https://erfgoed.utrecht.nl:443"}}, 
        {"template-id": "typo3-detect", "name": "TYPO3 Detection", "finding-name": "nuclei_typo3_detect", "evidence": {"extracted-results": [], "matched-at": "https://erfgoed.utrecht.nl:443"}}] 
    """,  # noqa
    )
    url4 = create_sample_data_for_url(
        "serviscope-acc.kpn.com",
        "nuclei_technologies",
        """[
        {"template-id": "tech-detect", "name": "Wappalyzer Technology Detection", "finding-name": "nuclei_tech_detect_awselb", "evidence": {"extracted-results": [], "matched-at": "https://serviscope-acc.kpn.com:443"}}]
    """,  # noqa
    )

    task = compose_verify_task(
        [url1, url2, url3, url4],
        {"args": []},
    )

    out = str(task)
    # 5 scans means 5 re-scans
    assert str(task).count("nuclei_http.scan") == 5

    # make the output a bit shorter to make easier comparisons:
    out = out.replace("{'args': [{'name': 'template-id', 'type': 'list-to-duplicate-arguments', ", "")
    out = out.replace("'value':", "")
    import re

    out = re.sub(r"[^A-Za-z0-9 ]+", "", out)

    log.debug(out)
    assert "httpserviscopeacckpncom443  techdetect" in out  # noqa
    assert "httpmailrhcvechtenvenennl443  apachedetect wafdetect" in out  # noqa
    assert 1 == out.count("httpmailrhcvechtenvenennl443  phpmyadminpanel")  # noqa
    assert 1 == out.count("httperfgoedutrechtnl443  metatagcms techdetect typo3detect")  # noqa
    assert 1 == out.count("httptwomnibuzznl443  apachedetect favicondetect wafdetect")  # noqa


@override_config(NUCLEI_HTTP_DISABLED_TEMPLATES='["robots-txt", "security-txt"]')
def test_create_nuclei_scan_command(db):

    command = create_nuclei_scan_command(
        ["test.nl"],
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
        "-u",
        "test.nl",
    ]
