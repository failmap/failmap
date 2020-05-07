import logging
from datetime import datetime, timedelta

from websecmap.organizations.models import Url
from websecmap.scanners.models import (Endpoint, EndpointGenericScan, InternetNLV2Scan,
                                       InternetNLV2StateLog)
from websecmap.scanners.scanner.internet_nl_v2_websecmap import (initialize_scan,
                                                                 process_scan_results,
                                                                 progress_running_scan,
                                                                 update_state)

log = logging.getLogger('websecmap')


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
    update_state(scan, "configuration_error", "This is a recoverable error, and when progressing, the first valid state"
                                              "will be requested")

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
    update_state(scan, "running scan", "When an error occurs, a progress will move to running scan, and not to "
                                       "requested")
    update_state(scan, "configuration_error", "oh no!")
    progress_running_scan(scan)

    # recoverable state, error and retry of recoverable state
    assert InternetNLV2StateLog.objects.all().count() == 11

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "running scan"


def test_internet_nl_store_testresults(db):
    test_results = {'secure.aalten.nl': {
        'report': {'url': 'https://dev.batch.internet.nl/site/secure.aalten.nl/665357/'}, 'scoring': {'percentage': 48},
        'results': {'categories': {'web_ipv6': {'verdict': 'failed', 'status': 'failed'},
                                   'web_dnssec': {'verdict': 'passed', 'status': 'passed'},
                                   'web_https': {'verdict': 'failed', 'status': 'failed'},
                                   'web_appsecpriv': {'verdict': 'warning', 'status': 'warning'}}, 'tests': {
            'web_ipv6_ns_address': {'status': 'passed', 'verdict': 'good',
                                    'technical_details': [['ns2.transip.eu.', '2a01:7c8:f:c1f::195', '37.97.199.195'],
                                                          ['ns0.transip.net.', '2a01:7c8:dddd:195::195',
                                                           '195.135.195.195'],
                                                          ['ns1.transip.nl.', '2a01:7c8:7000:195::195',
                                                           '195.8.195.195']]},
            'web_ipv6_ns_reach': {'status': 'passed', 'verdict': 'good', 'technical_details': []},
            'web_ipv6_ws_address': {'status': 'failed', 'verdict': 'bad',
                                    'technical_details': [['secure.aalten.nl', 'None', 'None']]},
            'web_ipv6_ws_reach': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_ipv6_ws_similar': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_dnssec_exist': {'status': 'passed', 'verdict': 'good',
                                 'technical_details': [['secure.aalten.nl', 'None']]},
            'web_dnssec_valid': {'status': 'passed', 'verdict': 'good',
                                 'technical_details': [['secure.aalten.nl', 'secure']]},
            'web_https_http_available': {'status': 'failed', 'verdict': 'bad', 'technical_details': []},
            'web_https_http_redirect': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_http_hsts': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_http_compress': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_keyexchange': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_ciphers': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_cipherorder': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_version': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_compression': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_secreneg': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_clientreneg': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_cert_chain': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_cert_pubkey': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_cert_sig': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_cert_domain': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_dane_exist': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_dane_valid': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_0rtt': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_ocsp': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_https_tls_keyexchangehash': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_appsecpriv_x_frame_options': {'status': 'not_tested', 'verdict': 'not-tested',
                                               'technical_details': []},
            'web_appsecpriv_referrer_policy': {'status': 'not_tested', 'verdict': 'not-tested',
                                               'technical_details': []},
            'web_appsecpriv_csp': {'status': 'not_tested', 'verdict': 'not-tested', 'technical_details': []},
            'web_appsecpriv_x_content_type_options': {'status': 'not_tested', 'verdict': 'not-tested',
                                                      'technical_details': []},
            'web_appsecpriv_x_xss_protection': {'status': 'not_tested', 'verdict': 'not-tested',
                                                'technical_details': []}}, 'custom': {}}}, 'lyncdiscover.vng.nl': {
        'report': {'url': 'https://dev.batch.internet.nl/site/lyncdiscover.vng.nl/665166/'},
        'scoring': {'percentage': 66}, 'results': {'categories': {'web_ipv6': {'verdict': 'passed', 'status': 'passed'},
                                                                  'web_dnssec': {'verdict': 'failed',
                                                                                 'status': 'failed'},
                                                                  'web_https': {'verdict': 'failed',
                                                                                'status': 'failed'},
                                                                  'web_appsecpriv': {'verdict': 'warning',
                                                                                     'status': 'warning'}}, 'tests': {
            'web_ipv6_ns_address': {'status': 'passed', 'verdict': 'good', 'technical_details': [
                ['ns3.yourdomainprovider.net.', '2604:a880:800:10::9a1:2001', '104.236.29.251'],
                ['ns1.yourdomainprovider.net.', '2a01:448:1::65:53', '213.249.65.53'],
                ['ns2.yourdomainprovider.net.', '2a03:b0c0:3:d0::124:5001', '46.101.153.24']]},
            'web_ipv6_ns_reach': {'status': 'passed', 'verdict': 'good', 'technical_details': []},
            'web_ipv6_ws_address': {'status': 'passed', 'verdict': 'good',
                                    'technical_details': [['lyncdiscover.vng.nl', '2603:1027::e', '52.112.193.16']]},
            'web_ipv6_ws_reach': {'status': 'passed', 'verdict': 'good', 'technical_details': []},
            'web_ipv6_ws_similar': {'status': 'passed', 'verdict': 'good', 'technical_details': []},
            'web_dnssec_exist': {'status': 'failed', 'verdict': 'bad',
                                 'technical_details': [['lyncdiscover.vng.nl', 'None']]},
            'web_dnssec_valid': {'status': 'not_tested', 'verdict': 'not-tested',
                                 'technical_details': [['lyncdiscover.vng.nl', 'insecure']]},
            'web_https_http_available': {'status': 'passed', 'verdict': 'good',
                                         'technical_details': [['2603:1027::e', 'yes'], ['52.112.196.45', 'yes']]},
            'web_https_http_redirect': {'status': 'failed', 'verdict': 'bad',
                                        'technical_details': [['2603:1027::e', 'no'], ['52.112.196.45', 'no']]},
            'web_https_http_hsts': {'status': 'failed', 'verdict': 'bad',
                                    'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_https_http_compress': {'status': 'info', 'verdict': 'bad',
                                        'technical_details': [['2603:1027::e', 'yes'], ['52.112.196.45', 'yes']]},
            'web_https_tls_keyexchange': {'status': 'passed', 'verdict': 'good',
                                          'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_https_tls_ciphers': {'status': 'warning', 'verdict': 'phase-out',
                                      'technical_details': [['2603:1027::e', 'AES128-GCM-SHA256', 'phase out'],
                                                            ['...', 'AES128-SHA256', 'phase out'],
                                                            ['...', 'AES256-SHA', 'phase out'],
                                                            ['...', 'AES128-SHA', 'phase out'],
                                                            ['...', 'AES256-SHA256', 'phase out'],
                                                            ['...', 'AES256-GCM-SHA384', 'phase out'],
                                                            ['52.112.196.45', 'AES128-GCM-SHA256', 'phase out'],
                                                            ['...', 'AES128-SHA256', 'phase out'],
                                                            ['...', 'AES256-SHA', 'phase out'],
                                                            ['...', 'AES128-SHA', 'phase out'],
                                                            ['...', 'AES256-SHA256', 'phase out'],
                                                            ['...', 'AES256-GCM-SHA384', 'phase out']]},
            'web_https_tls_cipherorder': {'status': 'warning', 'verdict': 'warning',
                                          'technical_details': [['2603:1027::e', 'ECDHE-RSA-AES128-SHA256', ' '],
                                                                ['...', 'ECDHE-RSA-AES256-SHA', 4],
                                                                ['52.112.196.45', 'ECDHE-RSA-AES128-SHA256', ' '],
                                                                ['...', 'ECDHE-RSA-AES256-SHA', 4]]},
            'web_https_tls_version': {'status': 'warning', 'verdict': 'phase-out',
                                      'technical_details': [['2603:1027::e', 'TLS 1.1', 'phase out'],
                                                            ['...', 'TLS 1.0', 'phase out'],
                                                            ['52.112.196.45', 'TLS 1.1', 'phase out'],
                                                            ['...', 'TLS 1.0', 'phase out']]},
            'web_https_tls_compression': {'status': 'passed', 'verdict': 'good',
                                          'technical_details': [['2603:1027::e', 'no'], ['52.112.196.45', 'no']]},
            'web_https_tls_secreneg': {'status': 'passed', 'verdict': 'good',
                                       'technical_details': [['2603:1027::e', 'yes'], ['52.112.196.45', 'yes']]},
            'web_https_tls_clientreneg': {'status': 'passed', 'verdict': 'good',
                                          'technical_details': [['2603:1027::e', 'no'], ['52.112.196.45', 'no']]},
            'web_https_cert_chain': {'status': 'passed', 'verdict': 'good',
                                     'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_https_cert_pubkey': {'status': 'passed', 'verdict': 'good',
                                      'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_https_cert_sig': {'status': 'passed', 'verdict': 'good',
                                   'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_https_cert_domain': {'status': 'failed', 'verdict': 'bad',
                                      'technical_details': [['2603:1027::e', '*.online.lync.com'],
                                                            ['...', 'meet.lync.com'], ['...', '*.infra.lync.com'],
                                                            ['...', 'sched.lync.com'], ['...', '*.lync.com'],
                                                            ['52.112.196.45', '*.online.lync.com'],
                                                            ['...', 'meet.lync.com'], ['...', '*.infra.lync.com'],
                                                            ['...', 'sched.lync.com'], ['...', '*.lync.com']]},
            'web_https_dane_exist': {'status': 'info', 'verdict': 'bad',
                                     'technical_details': [['2603:1027::e', 'no'], ['52.112.196.45', 'no']]},
            'web_https_dane_valid': {'status': 'not_tested', 'verdict': 'not-tested',
                                     'technical_details': [['2603:1027::e', 'not tested'],
                                                           ['52.112.196.45', 'not tested']]},
            'web_https_tls_0rtt': {'status': 'passed', 'verdict': 'na',
                                   'technical_details': [['2603:1027::e', 'no'], ['52.112.196.45', 'no']]},
            'web_https_tls_ocsp': {'status': 'passed', 'verdict': 'good',
                                   'technical_details': [['2603:1027::e', 'yes'], ['52.112.196.45', 'yes']]},
            'web_https_tls_keyexchangehash': {'status': 'passed', 'verdict': 'good',
                                              'technical_details': [['2603:1027::e', 'yes'], ['52.112.196.45', 'yes']]},
            'web_appsecpriv_x_frame_options': {'status': 'warning', 'verdict': 'bad',
                                               'technical_details': [['2603:1027::e', 'None'],
                                                                     ['52.112.196.45', 'None']]},
            'web_appsecpriv_referrer_policy': {'status': 'warning', 'verdict': 'bad',
                                               'technical_details': [['2603:1027::e', 'None'],
                                                                     ['52.112.196.45', 'None']]},
            'web_appsecpriv_csp': {'status': 'info', 'verdict': 'bad',
                                   'technical_details': [['2603:1027::e', 'None'], ['52.112.196.45', 'None']]},
            'web_appsecpriv_x_content_type_options': {'status': 'passed', 'verdict': 'good',
                                                      'technical_details': [['2603:1027::e', 'nosniff'],
                                                                            ['52.112.196.45', 'nosniff']]},
            'web_appsecpriv_x_xss_protection': {'status': 'warning', 'verdict': 'bad',
                                                'technical_details': [['2603:1027::e', 'None'],
                                                                      ['52.112.196.45', 'None']]}}, 'custom': {}}}}

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

    # is there a series of imports?
    assert EndpointGenericScan.objects.all().count() == 90

    # are the web scans imported
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_appsecpriv_x_xss_protection").count() == 2

    # have the legacy views run?
    assert EndpointGenericScan.objects.all().filter(type="internet_nl_web_legacy_dnssec").count() == 2