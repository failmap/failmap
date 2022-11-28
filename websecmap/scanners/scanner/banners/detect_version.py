import json
import re
from json import JSONDecodeError

from websecmap.app import log
from websecmap.app.constance import constance_cached_value

SERVICE_IDENTITY_LIKELY_VERSION_FOUND = "service_identity_likely_version_found"  # high
SERVICE_IDENTITY_SOME_IDENTITY_FOUND = "service_identity_some_identity_found"  # low

# todo: support ips where all banners are missing, in that case add a service_identity_nothing_found.
SERVICE_IDENTITY_NO_BANNER_FOUND = "service_identity_nothing_found"  # good
SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE = "service_identity_not_seen_in_a_while"  # good


def detect_a_likely_version(banner: str, protocol: str):
    """
    This is a heuristic to see if a version can be detected in a string.

    We prefer NO banner to be available. So if you have a banner, that means some kind of penalty.
    So if you have 'apache' that is saying something: an attacker should have to guess (or header detect) if it's
    apache/ngnix/iis/lotus domino webserver. We expect to see _NOTHING_ in the banner.

    Versions are usually numbers. If you have some complex numbers in your banner, than it's likely to be a version.
    """
    conclusion = SERVICE_IDENTITY_NO_BANNER_FOUND

    banner = str(clean_banner(banner, protocol))

    if banner:
        # any banner is not good. so:
        conclusion = SERVICE_IDENTITY_SOME_IDENTITY_FOUND

        if any(map(str.isdigit, banner)):
            conclusion = SERVICE_IDENTITY_LIKELY_VERSION_FOUND

            # add exceptions for "apache2" for example.
            # todo: this should come from constance, there is a lot of movement in this list.
            # it should not include products that are very old, as those are not supported and thus broken
            generic_banners = [
                "amazons3",
                "apache",
                "apache/2",
                "iis7",
                "layer7-api-gateway",
                "microsoft-httpapi/2.0",
                "microsoft-iis/7.0",
                "microsoft-iis/8.5",
                "microsoft-iis/10.0",
                "nginx",
                "parallels html5 client" "smtp2go",
            ]

            try:
                extra_banners = json.loads(constance_cached_value("BANNERGRAB_GENERIC_BANNERS"))
                generic_banners = generic_banners + extra_banners
            except JSONDecodeError:
                log.error("BANNERGRAB_GENERIC_BANNERS is not valid json. Make sure it's lower case and valid json.")

            if banner in generic_banners:
                conclusion = SERVICE_IDENTITY_SOME_IDENTITY_FOUND

        if "version" in banner:
            conclusion = SERVICE_IDENTITY_LIKELY_VERSION_FOUND

    return conclusion


def clean_banner(banner, protocol: str):
    # destroys 509 info, but that is not the scope here
    banner = banner.lower()

    if protocol == "http":
        banner = remove_junk_http_headers(banner)

    if protocol == "ftp":
        banner = remove_ftp_command_numbers(banner)

    banner = remove_junk_data(banner)
    # try not to mistake ip-addresses with a version number.
    banner = remove_ip_addresses(banner)

    return banner


def remove_junk_http_headers(banner):
    # Skip http responses. These might contain 'server' in the header,
    # but thats usually also read on an alternative port

    if banner.startswith("HTTP/1.0"):
        return ""

    if banner.startswith("HTTP/1.1"):
        return ""

    return banner


def remove_ftp_command_numbers(banner):
    # d	220 Microsoft FTP Service 234 AUTH command ok. Expecting TLS Negotiation.
    banner = banner.replace("220", "")
    banner = banner.replace("234", "")
    return banner


def remove_ip_addresses(banner):
    # ipv4
    banner = re.sub(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", "", banner)
    # ipv6
    banner = re.sub(
        r"(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:"
        r"[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:)"
        r"{1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:)"
        r"{1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|"
        r"fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9])"
        r"{0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1"
        r"{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))",
        "",
        banner,
    )

    return banner


def remove_junk_data(banner):
    if "\u0000" in banner:
        """"""

    return banner
