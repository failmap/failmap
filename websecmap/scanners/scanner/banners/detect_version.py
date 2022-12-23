import json
import re
from json import JSONDecodeError
from websecmap.celery import EXPIRES_IN_ONE_DAY, app

from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import EndpointGenericScan

SERVICE_IDENTITY_LIKELY_VERSION_FOUND = "service_identity_likely_version_found"  # high
SERVICE_IDENTITY_SOME_IDENTITY_FOUND = "service_identity_some_identity_found"  # low

# todo: support ips where all banners are missing, in that case add a service_identity_nothing_found.
SERVICE_IDENTITY_NO_BANNER_FOUND = "service_identity_nothing_found"  # good
SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE = "service_identity_not_seen_in_a_while"  # good


"""
Some examples:
"Microsoft-IIS/10.0",
"Microsoft-HTTPAPI/2.0",
"Microsoft-IIS/8.5",
"SSH-2.0-OpenSSH_7.4",
"awselb/2.0",
"Microsoft-Azure-Application-Gateway/v2",
"nginx/1.18.0 (Ubuntu)",
"SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5",
"Apache2 Ubuntu Default Page: It works",
"Apache/2.4.29 (Ubuntu)",
"Apache/2.4.41 (Ubuntu)",
"SSH-2.0-OpenSSH_8.0",
"SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.7",
"SSH-2.0-Platform.sh",
"nginx/1.18.0",
"SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5",
"nginx/1.20.1",
"nginx/1.10.3 (Ubuntu)",
"Apache/2.4.54 (Debian)",
"SSH-2.0-OpenSSH_7.2p2 Ubuntu-4ubuntu2.10",
"Apache/2.4.18 (Ubuntu)",
"SSH-2.0-OpenSSH_7.9p1 Debian-10+deb10u2",
"SSH-2.0-OpenSSH_6.6.1",
"SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u1",
"nginx/1.14.0 (Ubuntu)",
"SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.4",
"SSH-2.0-sshreverseproxy",
"SSH-2.0-OpenSSH_6.6.1p1 Ubuntu-2ubuntu2.13",
"Layer7-API-Gateway",
"Microsoft-IIS/7.5",
"Microsoft-IIS/8.0",
"SSH-2.0-OpenSSH_for_Windows_8.0",
"SMTP2GO",
"SSH-2.0-OpenSSH_7.2p2 Ubuntu-4ubuntu2.8",
"503 Service Temporarily Unavailable",
"Apache/2.4.46 (Ubuntu)",
"SSH-2.0-OpenSSH_8.9p1 Ubuntu-3",
"SSH-2.0-OpenSSH_7.5 FreeBSD-20170903",
"Apache/2.4.7 (Ubuntu)",
"SSH-2.0-OpenSSH_7.2p2 Ubuntu-4ubuntu2.10+esm2",
"Apache/2.4.6 (CentOS) OpenSSL/1.0.2k-fips",
"SSH-2.0-OpenSSH_8.2p1",
"nginx/1.17.0",
"SSH-2.0-CerberusFTPServer_12.0",
"SSH-2.0-OpenSSH_4.3",
"Apache/2.4.52 (Ubuntu)",
"SSH-2.0-OpenSSH_7.9",
"SSH-2.0-mod_sftp",
"502 Bad Gateway",
"Tengine/2.2.1",
"SSH-2.0-OpenSSH_5.3",
"SSH-2.0-OpenSSH_7.2 FreeBSD-20161230",
"AmazonS3",
"nginx/1.15.6",
"Play! Framework;1.4.2;prod",
"Parallels HTML5 Client",
"303 See Other",
"Apache/2.4.54 (Fedora Linux) OpenSSL/1.1.1q mod_perl/2.0.12 Perl/v5.34.1",
"SSH-2.0-Syncplify_Me_Server",
"Apache/2.4.6 (Red Hat Enterprise Linux)",
"Microsoft-IIS/7.0",
"IIS7",
"SSH-2.0-8.44 FlowSsh: Bitvise SSH Server (WinSSHD) 8.44",
"SSH-2.0-OpenSSH_7.6p1 Ubuntu-4",
"SSH-2.0-OpenSSH_6.6.1p1 Ubuntu-2ubuntu2.6",
"s<%q1U {,f\r\nwc@~_<.|fx|SS6xmQ7ir\r\n$fc.`$@i[.cR*f(mq2UNC]*\r\n",
"SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.3",
"SSH-2.0-OpenSSH_8.4p1",
"10.103.50.3 - /",
"Apache/2.4.25 (Debian)",
"Microsoft-IIS/5.0",
"Apache/2.4.37 (FreeBSD) PHP/5.6.38",
"192.168.10.5 - /",
"~.\r\n>?Z)8..R^jKD\r\nlW1g3\r\n",
"nginx/1.10.3",
"SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.3",
"Apache/2.4.38 (Debian)",
"Park1: Deze website is geregistreerd voor een van onze klanten",
"Apache/2.2.16 (Debian)",
"Nieuwland Vangnet voor: \nNotice: Undefined index: HTTP_HOST in /srv/www/vangnet/htdocs/index.php on line 10\n",
"glass/1.0 Python/2.6.4",
"nginx/1.23.2",
"Apache/2.4.6 (CentOS) OpenSSL/1.0.2k-fips mod_fcgid/2.3.9 PHP/5.4.16",
"192.168.251.11 - /",
"SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.2",
"504 Gateway Time-out",
"Apache/2.4.46 (FreeBSD) OpenSSL/1.1.1g-freebsd PHP/7.4.12",
"nginx/1.21.4",
"Apache/2.4.41",
"Apache/2.2.22 (Ubuntu)",
"nginx/1.14.2",
"nginx/1.18.0 + Phusion Passenger(R) 6.0.12",
"""


def contains_version_number(banner):
    # A version number usually contains a digit and a dot. Something like 2.4. Some semantic versioning can easily
    # be detected as well.

    # semantic version, very high certainty
    matches = re.search(r"\d+\.\d+\.\d+", banner)
    if matches:
        log.debug("Detected version: %s", matches)
        return True

    # A little less certain:
    matches = re.search(r"(\d+\.\d+)", banner)
    if matches:
        log.debug("Detected version: %s", matches)
        return True

    return False


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def re_evaluate_bannergrab_versions():
    # Walk over all latest scans with version information. Then re-run the detect_version command and save the

    changes = 0

    scans = (
        EndpointGenericScan.objects.all()
        .filter(type="bannergrab", is_the_latest_scan=True)
        .only("rating", "id", "evidence", "endpoint__protocol")
    )

    for scan in scans:
        # remove possible confidential data such as ip addresses, and remove garbage such as http responses
        # Rules might have been changed on re-evaluation. This editing is destructive.
        banner = clean_banner(scan.evidence, scan.endpoint.protocol)
        scan.evidence = banner

        conclusion = detect_a_likely_version(scan.evidence, scan.endpoint.protocol)

        if conclusion == scan.rating:
            log.debug("Scan has still the same conclusion for version %s: %s", scan.evidence, conclusion)
            continue

        changes += 1
        log.debug("Scan has a new conclusion for version %s: %s", scan.evidence, conclusion)
        scan.rating = conclusion
        scan.save(update_fields=["rating", "evidence"])

    log.debug("Changed %s version conclusions", changes)
    return changes


def detect_a_likely_version(banner: str, protocol: str):
    """
    This is a heuristic to see if a version can be detected in a string.

    We prefer NO banner to be available. So if you have a banner, that means some kind of penalty.
    So if you have 'apache' that is saying something: an attacker should have to guess (or header detect) if it's
    apache/ngnix/iis/lotus domino webserver. We expect to see _NOTHING_ in the banner.

    Versions are usually numbers. If you have some complex numbers in your banner, than it's likely to be a version.
    """

    # remove possible confidential data such as ip addresses, and remove garbage such as http responses
    banner = clean_banner(banner, protocol)

    if not banner:
        return SERVICE_IDENTITY_NO_BANNER_FOUND

    if "version" in banner:
        return SERVICE_IDENTITY_LIKELY_VERSION_FOUND

    if banner in excepted_banners() + get_dynamic_excepted_banners():
        return SERVICE_IDENTITY_SOME_IDENTITY_FOUND

    if contains_version_number(banner):
        return SERVICE_IDENTITY_LIKELY_VERSION_FOUND

    return SERVICE_IDENTITY_SOME_IDENTITY_FOUND


def excepted_banners():
    return [
        # large service providers
        "amazons3",
        "awselb/2.0",
        # proxies
        "layer7-api-gateway",
        # open source webservers
        "apache",
        "apache/2",
        "nginx",
        # microsoft, but not iis6.
        "microsoft httpapi httpd 2.0",
        "microsoft-httpapi/2.0",
        "microsoft-iis/7.0",
        "microsoft-iis/8.5",
        "microsoft-iis/10.0",
        "iis7",
        # popular products
        "haproxy http proxy 1.3.1 or later",
        "parallels html5 client",
        "smtp2go",
        # ssh
        "ssh-2.0-platform.sh",
        "ssh-2.0-sshreverseproxy",
        # props to alkmaar municipality :)
        "alk",
    ]


def get_dynamic_excepted_banners():
    try:
        return json.loads(constance_cached_value("BANNERGRAB_GENERIC_BANNERS"))
    except JSONDecodeError:
        log.error("BANNERGRAB_GENERIC_BANNERS is not valid json. Make sure it's lower case and valid json.")
        return []


def clean_banner(banner, protocol: str) -> str:
    # destroys 509 info, but that is not the scope here
    banner = banner.lower().strip()

    if cleaner := PROTOCOL_CLEANERS.get(protocol, None):
        banner = cleaner(banner)

    banner = remove_junk_data(banner)

    # try not to mistake ip-addresses with a version number.
    banner = remove_ip_addresses(banner)

    # very long texts are *usually* not a banner
    if len(banner) > 2000:
        banner = ""

    return str(banner).strip()


def remove_junk_http_headers(banner):
    # Skip http responses. These might contain 'server' in the header,
    # but thats usually also read on an alternative port

    if banner.startswith("http/"):
        return ""

    return banner


def remove_ftp_command_numbers(banner):
    # d	220 Microsoft FTP Service 234 AUTH command ok. Expecting TLS Negotiation.
    banner = banner.replace("220", "")
    banner = banner.replace("234", "")
    return banner


def remove_smtp_command_numbers(banner):
    # d	220 Microsoft FTP Service 234 AUTH command ok. Expecting TLS Negotiation.
    banner = banner.replace("220", "")
    return banner


def remove_ip_addresses(banner):
    # Do not give a hint that there ever WAS an IP address, as that can be scraped by others afterwards still,..
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
        banner = ""

    banner = banner.replace("<empty>", "").strip()

    if banner == "<empty>":
        banner = ""

    return banner


PROTOCOL_CLEANERS = {
    "ftp": remove_ftp_command_numbers,
    "http": remove_junk_http_headers,
    "https": remove_junk_http_headers,
    # looks like http traffic
    "tcpwrapped": remove_junk_http_headers,
    "smtp": remove_smtp_command_numbers,
}
