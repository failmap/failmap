"""
A list of all scan types that are reliable and can be used in production environments (reporting, etc).
"""
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
    'DNSSEC'
]

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# Beta scanners are:
# screenshot, osaft, some of these are not endpoint or URL types.
