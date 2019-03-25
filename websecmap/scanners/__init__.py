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


SCANNERS = [
    {
        'name': 'ftp',
        'verbose name': 'File Transfer Protocol (FTP)',
        'description': 'Scans FTP services on port 21 (default port) if they support TLS or SSL.',
        'can discover endpoints': True,
        'can verify endpoints': True,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': ['ftp'],
        'creates url scan types': [],
    },
    {
        'name': 'internet_nl_mail',
        'verbose name': 'Scan recipient for STARTTLS, SPF, DKIM and DMARC using internet.nl',
        'description': 'Scans the mail server in the MX record to see if they support STARTTLS, SPF, DKIM and DMARC. '
                       'Requires internet.nl scan account.',
        'can discover endpoints': True,
        'can verify endpoints': True,

        # finds if there are MX records on url, pre scan and during scan.
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': [
            'internet_nl_mail_starttls_tls_available',
            'internet_nl_mail_auth_spf_exist',
            'internet_nl_mail_auth_dkim_exist',
            'internet_nl_mail_auth_dmarc_exist'],
        'creates url scan types': []
    },
    {
        'name': 'plain_http',
        'verbose name': 'Missing Encryption',
        'description': 'Scans HTTP endpoints to see if there is an HTTPS counterpart.',
        'can discover endpoints': True,
        'can verify endpoints': True,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': ['plain_https'],
        'creates url scan types': [],
    },
    {
        'name': 'dnssec',
        'verbose name': 'Domain Name Security (DNSSEC)',
        'description': 'Scans DNS records to see if Domain Name security (DNSSEC) is enabled and secure',
        'can discover endpoints': False,
        'can verify endpoints': False,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': [],
        'creates url scan types': ['DNSSEC'],
    },
    {
        'name': 'security_headers',
        'verbose name': 'Website security settings (HTTP headers)',
        # todo?? cant verify?
        'description': 'Contacts HTTP services to determine if all security headers are enabled.',
        'can discover endpoints': False,
        'can verify endpoints': False,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': ['http_security_header_strict_transport_security',
                                        'http_security_header_x_content_type_options',
                                        'http_security_header_x_frame_options',
                                        'http_security_header_x_xss_protection'],
        'creates url scan types': [],
    },
    {
        'name': 'tls_qualys',
        'verbose name': 'Encryption Quality Scans (TLS, tested with Qualys)',
        'description': 'Scans HTTPS services on port 443 to find the quality and security on it\'s encryption. '
                       'Contacts Qualys for each scan.',
        'can discover endpoints': False,
        'can verify endpoints': False,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': ['tls_qualys_certificate_trusted', 'tls_qualys_encryption_quality'],
        'creates url scan types': [],
    },
    {
        'name': 'dns',
        'verbose name': 'Discover subdomains using open data sources',
        'description': 'Uses NSEC1 and Certificate Tranparency to discover new urls. '
        'About NSEC1: Discover new domains using DNSSEC NSEC1 enumeration. This is a powerful but not frequently used '
                       'feature '
        'that allows you to sometimes discover all subdomains of a domain. This check is very fast and results '
        'in a complete set of domains. Might not be used by the owner of the domain, in that case it will '
        'return no subdomains.'
        ''
        'About Certificate Transparency: This discovery method searches for certificates published on a domain. '
        'When a website uses https, the request '
        'for a new certificate is published publicly as part of the Certiificate Transparency program. Using the '
        'public database of all requests, it\'s possible to find hundreds of subdomains for a domain.'
        '<br><br>The service used is crt.sh.',
        'can discover endpoints': False,
        'can verify endpoints': False,
        'can discover urls': True,
        'can verify urls': True,
        'creates endpoint scan types': [],
        'creates url scan types': [],
    },
    {
        'name': 'dns_known_subdomains',
        'verbose name': 'Subdomain discovery using known subdomains',
        'description': 'Attempts to contact the list of known subdomains on other domains. ',
        'can discover endpoints': False,
        'can verify endpoints': False,
        'can discover urls': True,
        'can verify urls': False,
        'creates endpoint scan types': [],
        'creates url scan types': [],
    },
    {
        'name': 'http',
        'verbose name': 'HTTP/HTTPS Endpoint discovery',
        'description': 'Discovers and verifies the existence of HTTP/HTTPS services on standard and alternative ports.',
        'can discover endpoints': True,
        'can verify endpoints': True,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': [],
        'creates url scan types': [],
    },
    {
        'name': 'verify_unresolvable',
        'verbose name': 'Verify that unresolvable domains still not resolve',
        'description': 'Checks that the urls that are unresolvable are still unresolvable (counters network-bugs)',
        'can discover endpoints': False,
        'can verify endpoints': True,
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': [],
        'creates url scan types': [],
    },
    {
        'name': 'onboard',
        'verbose name': 'Onboard new urls with several scans, crawling and reporting',
        'description': 'Runs several scanners to automatically discover domains, run scans and create reports.',
        'can discover endpoints': True,
        'can verify endpoints': False,
        'can discover urls': True,
        'can verify urls': False,

        # don't re-hash the same scan types. This scanner simply uses other scanners which changes over time
        # to reduce complexity, this scanner creates no scan types specifically.
        'creates endpoint scan types': [],
        'creates url scan types': [],
    },
    {
        'name': 'internet_nl_web',
        'verbose name': 'Scans websites on basic HTTP security (Tested with internet.nl)',
        'description': 't.b.d.',
        'can discover endpoints': False,
        'can verify endpoints': False,

        # finds if there are MX records on url, pre scan and during scan.
        'can discover urls': False,
        'can verify urls': False,
        'creates endpoint scan types': [],
        'creates url scan types': ['internet_nl_web_web_ipv6_ws_similar']
    },
]

BETA_SCANNERS = ['tls_osaft', 'screenshot']

# todo: should we move the scanner definitions to different scanners and harvest them here?

# todo: we're missing a separate nsec scanner it seems, should be separated from DNS scans.
# todo: add beta scanners, for which no permission checks are needed at all.
# not as relevant as this behavior is included in generic DNS scanning

AVAILABLE_SCANNERS = []
ENDPOINT_SCAN_TYPES = []
URL_SCAN_TYPES = []
for scanner in SCANNERS:
    AVAILABLE_SCANNERS += scanner['name']
    ENDPOINT_SCAN_TYPES = list(set(ENDPOINT_SCAN_TYPES + scanner["creates endpoint scan types"]))
    URL_SCAN_TYPES = list(set(URL_SCAN_TYPES + scanner["creates url scan types"]))

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# todo: add config options for each of the scans defined above, include them in constance.
# todo: check these config options dynamically at the right moments, so to reduce maintenance.
