import logging

import pytest

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.internet_nl_mail import (inject_legacy_views, store,
                                                         true_when_all_match, upgrade_api_response)

log = logging.getLogger('websecmap')


# The result from the documentation can be ignored, it's not up to date anymore.
# this result is from a real scan
mail_result = {
    "message": "OK",
    "data": {
        "name": "Failmap Scan 9b33a48d-3507-422d-b520-974a0bcdbcd8",
        "submission-date": "2018-11-22T09:45:07.274815+00:00",
        "api-version": "1.0",
        "domains": [
            {
                "status": "ok",
                "domain": "arnhem.nl",
                "views": [
                    {
                        "result": True,
                        "name": "mail_starttls_cert_domain"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_version"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_cert_chain"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_available"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_clientreneg"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_ciphers"
                    },
                    {
                        "result": False,
                        "name": "mail_starttls_dane_valid"
                    },
                    {
                        "result": False,
                        "name": "mail_starttls_dane_exist"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_secreneg"
                    },
                    {
                        "result": False,
                        "name": "mail_starttls_dane_rollover"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_cert_pubkey"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_cert_sig"
                    },
                    {
                        "result": True,
                        "name": "mail_starttls_tls_compress"
                    },
                    {
                        "result": False,
                        "name": "mail_starttls_tls_keyexchange"
                    },
                    {
                        "result": False,
                        "name": "mail_auth_dmarc_policy"
                    },
                    {
                        "result": True,
                        "name": "mail_auth_dmarc_exist"
                    },
                    {
                        "result": True,
                        "name": "mail_auth_spf_policy"
                    },
                    {
                        "result": True,
                        "name": "mail_auth_dkim_exist"
                    },
                    {
                        "result": True,
                        "name": "mail_auth_spf_exist"
                    },
                    {
                        "result": True,
                        "name": "mail_dnssec_mailto_exist"
                    },
                    {
                        "result": True,
                        "name": "mail_dnssec_mailto_valid"
                    },
                    {
                        "result": True,
                        "name": "mail_dnssec_mx_valid"
                    },
                    {
                        "result": True,
                        "name": "mail_dnssec_mx_exist"
                    },
                    {
                        "result": False,
                        "name": "mail_ipv6_mx_address"
                    },
                    {
                        "result": False,
                        "name": "mail_ipv6_mx_reach"
                    },
                    {
                        "result": True,
                        "name": "mail_ipv6_ns_reach"
                    },
                    {
                        "result": True,
                        "name": "mail_ipv6_ns_address"
                    },
                    {
                        "result": True,
                        "name": "mail_servers_testable"
                    },
                    # This will set the requirement to not applicable on a number of tests
                    {
                        "result": False,
                        "name": "mail_server_configured"
                    },
                    # This sets mail_starttls_cert_domain to required, which is overridden by being not required above
                    {
                        "result": True,
                        "name": "mail_starttls_dane_ta"
                    },
                    {
                        "result": False,
                        "name": 'mail_non_sending_domain',
                    }
                ],
                "score": 77,
                "link": "https://batch.internet.nl/mail/arnhem.nl/223685/",
                "categories": [
                    {
                        "category": "ipv6",
                        "passed": False
                    },
                    {
                        "category": "dnssec",
                        "passed": True
                    },
                    {
                        "category": "auth",
                        "passed": False
                    },
                    {
                        "category": "tls",
                        "passed": False
                    }
                ]
            }
        ],
        "finished-date": "2018-11-22T09:55:56.103073+00:00",
        "identifier": "e5ea54ede6ce42f5a20fad6d0b049d89"
    },
    "success": True
}

web_result = {
    "message": "OK",
    "data": {
        "name": "Internet.nl Dashboard, Type: Web, Account: Internet Cleanup Foundation, List: testsites c5555e21-5a21",
        "submission-date": "2019-03-28T09:52:43.907671+00:00", "api-version": "1.0",
        "domains":
            [
                {
                    "status": "ok",
                    "domain": "arnhem.nl",
                    "views": [{"result": True, "name": "web_https_cert_domain"},
                              {"result": False, "name": "web_https_http_redirect"},
                              {"result": True, "name": "web_https_cert_chain"},
                              {"result": True, "name": "web_https_tls_version"},
                              {"result": True, "name": "web_https_tls_clientreneg"},
                              {"result": True, "name": "web_https_tls_ciphers"},
                              {"result": True, "name": "web_https_http_available"},
                              {"result": False, "name": "web_https_dane_exist"},
                              {"result": True, "name": "web_https_http_compress"},
                              {"result": True, "name": "web_https_http_hsts"},
                              {"result": True, "name": "web_https_tls_secreneg"},
                              {"result": False, "name": "web_https_dane_valid"},
                              {"result": True, "name": "web_https_cert_pubkey"},
                              {"result": True, "name": "web_https_cert_sig"},
                              {"result": True, "name": "web_https_tls_compress"},
                              {"result": True, "name": "web_https_tls_keyexchange"},
                              {"result": True, "name": "web_dnssec_exist"},
                              {"result": True, "name": "web_dnssec_valid"},
                              {"result": False, "name": "web_ipv6_ns_address"},
                              {"result": False, "name": "web_ipv6_ws_similar"},
                              {"result": False, "name": "web_ipv6_ns_reach"},
                              {"result": False, "name": "web_ipv6_ws_address"},
                              {"result": False, "name": "web_ipv6_ws_reach"}],
                    "score": 63,
                    "link": "https://batch.internet.nl/site/hdsr.nl/535985/",
                    "categories": [
                        {"category": "ipv6", "passed": False},
                        {"category": "dnssec", "passed": True},
                        {"category": "tls", "passed": False}
                    ]
                },
            ],
        "finished-date": "2019-03-28T09:55:11.415837+00:00",
        "identifier": "ef69d623fbc649449f730bc15c643176"
    },
    "success": True
}


def reload_data(api_response, internet_nl_scan_type='mail'):
    EndpointGenericScan.objects.all().delete()
    Endpoint.objects.all().delete()
    Url.objects.all().delete()

    url, created = Url.objects.all().get_or_create(url='arnhem.nl')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol='dns_mx_no_cname')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol='dns_a_aaaa')
    store(api_response, internet_nl_scan_type)


def change_api_value(api_data, key="mail_server_configured", new_value=True):

    for domain in api_data['data']['domains']:
        for view in domain['views']:
            if view['name'] == key:
                view['result'] = new_value

    return api_data


def test_internet_nl_mail(db):
    # Make sure legacy views are injected in the results:
    domains = mail_result.get('data', {}).get('domains', {})

    has_legacy_view = False
    for domain in domains:
        assert domain['domain'] == 'arnhem.nl'
        assert len(domain['views']) == 31
        domain['views'] = inject_legacy_views('mail_dashboard', domain['views'])

        # changes true/false to requirement_level~result (includes not applicable / not testable)
        domain['views'] = upgrade_api_response(domain['views'])
        assert len(domain['views']) == 31 + 12

        for view in domain['views']:
            # internet_nl is added just before storing the scan result
            if view['name'] == "mail_legacy_ipv6_mailserver":
                has_legacy_view = True

    assert has_legacy_view is True

    # should not exist yet
    scan_count = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_ipv6_ns_address').count()
    assert scan_count == 0

    url, created = Url.objects.all().get_or_create(url='arnhem.nl')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol='dns_mx_no_cname')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol='dns_a_aaaa')

    # add 29 views, 4 categories, 1 score, 12 auto generated = 44
    # Amount of legacy items auto-generated: 12
    store(mail_result, internet_nl_scan_type='mail')
    scan_count = EndpointGenericScan.objects.all().filter().count()
    assert scan_count == 48

    # add 23 views, 1 score, 3 categories, 8 auto generated = 35
    store(web_result, internet_nl_scan_type='web')
    scan_count = EndpointGenericScan.objects.all().filter().count()
    assert scan_count == 48 + 35

    # Should be added once, scan result didn't change.
    store(mail_result, internet_nl_scan_type='mail')
    scan_count = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_ipv6_ns_address').count()
    assert scan_count == 1

    scan_count = EndpointGenericScan.objects.all().filter().count()
    assert scan_count == 48 + 35

    # retrieve a value, and see if it's using the updated format
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_ipv6_ns_address').get()
    assert epgs.rating == "required~passed"

    # This has been set to not_applicable in the test data, we emulate a non-sending domain
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_starttls_tls_ciphers').get()
    assert epgs.rating == "not_applicable~not_applicable"

    # required, but then overwritten to be not applicable
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_starttls_cert_domain').get()
    assert epgs.rating == "not_applicable~not_applicable"

    # now see that we can get a optional~passd for mail_starttls_cert_domain
    data = change_api_value(mail_result, "mail_starttls_dane_ta", True)

    # and we should check the internet_nl_mail_starttls_cert_domain for required~not_testable
    data = change_api_value(data, "mail_server_configured", True)
    data = change_api_value(data, "mail_servers_testable", False)
    reload_data(data)
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_starttls_cert_domain').get()
    assert epgs.rating == "required~not_testable"

    # verify that when mail_starttls_dane_ta is false, the internet_nl_mail_starttls_cert_domain becomes optional
    data = change_api_value(mail_result, "mail_starttls_dane_ta", False)
    reload_data(data)
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_starttls_cert_domain').get()
    assert epgs.rating == "optional~not_testable"

    # todo: verify that settings mail_non_sending_domain makes mail_auth_dkim_exist not applicable
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_auth_dkim_exist').get()
    assert epgs.rating == "required~passed"
    data = change_api_value(mail_result, "mail_non_sending_domain", True)
    reload_data(data)
    epgs = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_auth_dkim_exist').get()
    assert epgs.rating == "not_applicable~not_applicable"

    views = [
        {
            "result": False,
            "name": "mail_ipv6_mx_address"
        },
        {
            "result": False,
            "name": "mail_ipv6_mx_reach"
        },
        {
            "result": True,
            "name": "mail_ipv6_ns_reach"
        },
        {
            "result": True,
            "name": "mail_ipv6_ns_address"
        }
    ]

    # both true
    assert true_when_all_match(views, ['mail_ipv6_ns_reach', 'mail_ipv6_ns_address']) is True

    # one false
    assert true_when_all_match(views, ['mail_ipv6_ns_reach', 'mail_ipv6_mx_reach']) is False

    # both false
    assert true_when_all_match(views, ['mail_ipv6_mx_reach', 'mail_ipv6_mx_address']) is False

    with pytest.raises(ValueError, match=r'.*view.*'):
        assert true_when_all_match([], ['mail_ipv6_mx_reach', 'mail_ipv6_mx_address']) is False

    with pytest.raises(ValueError, match=r'.*values.*'):
        assert true_when_all_match(views, []) is False
