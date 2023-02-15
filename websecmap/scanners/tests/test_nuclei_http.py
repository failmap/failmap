from django.utils import timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.nuclei_http import (
    store,
    convert_nuclei_data_to_json,
    process_nuclei_record,
    prepare_nuclei_results_for_storage,
    get_higher_severity,
    neutralize_missing_metrics,
    split_nuclei_records_per_host,
)

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
    b":null}\n"
)


def test_nuclei_store(db, current_path):
    url = Url.objects.create(**{"url": "basisbeveiliging.nl"})
    end = Endpoint.objects.create(**{"url": url, "protocol": "https", "port": 443, "ip_version": 4})

    host_to_endpoint_mapping = {"https://basisbeveiliging.nl": {"endpoint": end.id, "url": url.id}}

    # no results should be no issue
    store(b"", host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 0

    # all categorized into the technologies area.
    store(three_example_nuclei_tests, host_to_endpoint_mapping)
    assert EndpointGenericScan.objects.count() == 1


def test_split_metrics_per_host():
    raw_nuclei_records = convert_nuclei_data_to_json(three_example_nuclei_tests)
    result = split_nuclei_records_per_host(raw_nuclei_records)
    assert len(result["https://basisbeveiliging.nl"]) == 3

    for x, y in result.items():
        assert len(y) == 3


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
    ]


def test_process_nuclei_record():
    processed = process_nuclei_record(
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
        }
    )

    assert processed == {
        "category": "technologies",
        "evidence": {
            "curl-command": "curl -X 'POST' -d '_=<script>alert(1)</script>' "
            "-H 'Content-Type: "
            "application/x-www-form-urlencoded' -H 'Host: "
            "basisbeveiliging.nl' -H 'User-Agent: "
            "Mozilla/5.0 (Windows NT 6.3; WOW64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/41.0.2225.0 Safari/537.36' "
            "'https://basisbeveiliging.nl/'",
            "extracted-results": [],
            "matched-at": "https://basisbeveiliging.nl/",
        },
        "finding-name": "nuclei_waf_detect_nginxgeneric",
        "name": "WAF Detection",
        "severity": "info",
    }

    processed = process_nuclei_record(
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
        }
    )

    assert processed == {
        "category": "technologies",
        "evidence": {
            "curl-command": "curl -X 'GET' -d '' -H 'Accept: */*' -H "
            "'Accept-Language: en' -H 'User-Agent: "
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/54.0.2866.71 Safari/537.36' "
            "'https://basisbeveiliging.nl'",
            "extracted-results": [],
            "matched-at": "https://basisbeveiliging.nl",
        },
        "finding-name": "nuclei_tech_detect_nginx",
        "name": "Wappalyzer Technology Detection",
        "severity": "info",
    }

    assert process_nuclei_record({}) == {
        "category": "unknown",
        "evidence": {"curl-command": "", "extracted-results": [], "matched-at": ""},
        "finding-name": "nuclei_unknown",
        "name": "unknown",
        "severity": "unknown",
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
                    "curl-command": "curl -X 'GET' "
                    "-d '' -H "
                    "'Accept: */*' "
                    "-H "
                    "'Accept-Language: "
                    "en' -H "
                    "'User-Agent: "
                    "Mozilla/5.0 "
                    "(Windows NT "
                    "6.1; WOW64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like "
                    "Gecko) "
                    "Chrome/36.0.1985.67 "
                    "Safari/537.36' "
                    "'https://www.example.com'",
                    "extracted-results": [],
                    "matched-at": "https://www.example.com",
                },
                "finding-name": "nuclei_drupal_login",
                "name": "Drupal Login Panel - Detect",
            },
            {
                "evidence": {
                    "curl-command": "curl -X 'GET' "
                    "-d '' -H "
                    "'Accept: */*' "
                    "-H "
                    "'Accept-Language: "
                    "en' -H "
                    "'User-Agent: "
                    "Mozilla/5.0 "
                    "(Windows NT "
                    "10.0; Win64; "
                    "x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like "
                    "Gecko) "
                    "Chrome/70.0.3538.77 "
                    "Safari/537.36' "
                    "'https://www.example.com/phpmyadmin/'",
                    "extracted-results": ["4.9.0.1"],
                    "matched-at": "https://www.example.com/phpmyadmin/",
                },
                "finding-name": "nuclei_phpmyadmin_panel",
                "name": "phpMyAdmin Panel - Detect",
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
    default = {"endpoint": endpoint, "is_the_latest_scan": True, "rating_determined_on": timezone.now()}
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
