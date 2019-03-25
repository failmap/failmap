from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.internet_nl_mail import store


# The result from the documentation can be ignored, it's not up to date anymore.
# this result is from a real scan
result = {
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


def test_internet_nl_mail(db):

    # should not exist yet
    scan_count = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_ipv6_ns_address').count()
    assert scan_count == 0

    url, created = Url.objects.all().get_or_create(url='arnhem.nl')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, port='25', protocol='mx_mail')

    store(result, internet_nl_scan_type='mail')

    # We've added 32 items, including the score and the categories
    scan_count = EndpointGenericScan.objects.all().filter().count()
    assert scan_count == 32

    # Should be added once
    scan_count = EndpointGenericScan.objects.all().filter(type='internet_nl_mail_ipv6_ns_address').count()
    assert scan_count == 1
