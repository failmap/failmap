"""
A list of all scan types that are reliable and can be used in production environments.
"""
ENDPOINT_SCAN_TYPES = [
    'Strict-Transport-Security',
    'X-Content-Type-Options',
    'X-Frame-Options',
    'X-XSS-Protection',
    'plain_https',
    'ftp',
    'tls_qualys_certificate_trusted',
    'tls_qualys_encryption_quality'
]

URL_SCAN_TYPES = [
    'DNSSEC'
]

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# Beta scanners are:
# screenshot, osaft
