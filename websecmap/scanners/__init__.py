"""
A list of all scan types that are reliable and can be used in production environments (reporting, etc).

If you want to add a new scanner, you'll have to go through the following steps.
- Add it to the correct list below (todo: automate discovery of what scanners are available)
- Add severities for these scans in reporting/severity.py
- Add configuration for the scans in settings.py (todo: automate) (optional?) default = true anyway.
- Add

scanner needs the following config:
DETAILS = {
    'name': 'arbitrary name',
    'endpoint scan types': ['internet_nl_mail_starttls_tls_available'],
    'url scan types': [],
    # standard options generated for each scanner are: allow scanning, allow reporting, allow displaying on site

    # then there are custom options.
    'options': {
        'DISCOVER_URLS_USING_KNOWN_SUBDOMAINS': (
            True,
            'Uses the list of known subdomains in your installation to discover the same subdomains on other domains. '
            '<br><br>For example: it will search "test" on every domain, if that is present in an existing url: '
            '"text.example.com".', bool)}

}

"""

# this is the lowest grain, per type.
ENDPOINT_SCAN_TYPES = [
    'http_security_header_strict_transport_security',
    'http_security_header_x_content_type_options',
    'http_security_header_x_frame_options',
    'http_security_header_x_xss_protection',
    'plain_https',
    'ftp',
    'tls_qualys_certificate_trusted',
    'tls_qualys_encryption_quality'
]

URL_SCAN_TYPES = [
    'DNSSEC',
    'internet_nl_mail_starttls_tls_available',
    'internet_nl_mail_spf',
    'internet_nl_mail_auth_dkim_exist',
    'internet_nl_mail_auth_dmarc_exist'
]

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# todo: add config options for each of the scans defined above, include them in constance.
# todo: check these config options dynamically at the right moments, so to reduce maintenance.
