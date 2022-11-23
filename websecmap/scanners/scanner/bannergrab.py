"""
Grabs banners (software versions) from a series of protocols. Filters them and adds them to findings.

This prevents attackers to find a simple version and monitor that until an exploit comes available. An
attacker has to put in more work. This is public information published by organizations. Let's hope
they use fake banners, that's much more fun :)

This scanner works differently than the other ones since it cannot be planned per domain. The used tool
is simply too fast for this kind of overhead. This is simply a periodic task.

For this to work a return-ip address needs to be specified. Otherwise the return packets will not be received.

Thank you Robert David Graham for your excellent work.

Masscan supports banner checking on the following protocols:

FTP
HTTP
IMAP4
memcached
POP3
SMTP
SSH
SSL
SMBv1
SMBv2
Telnet
RDP
VNC

http is by far the most interesting stuff, it's basically a mess

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
import json
from json import JSONDecodeError

import pytz

from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import UrlIp, EndpointGenericScan, Endpoint
from websecmap.scanners.scanmanager import store_endpoint_scan_result
import logging

from celery import Task, group

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.scanners import init_dict
from websecmap.scanners.scanner.__init__ import (
    allowed_to_scan,
)
import masscan
from datetime import datetime, timedelta
import re

SCANNER_NAME = "bannergrab"

SERVICE_IDENTITY_LIKELY_VERSION_FOUND = "service_identity_likely_version_found"  # high
SERVICE_IDENTITY_SOME_IDENTITY_FOUND = "service_identity_some_identity_found"  # low

# todo: support ips where all banners are missing, in that case add a service_identity_nothing_found.
SERVICE_IDENTITY_NO_BANNER_FOUND = "service_identity_nothing_found"  # good
SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE = "service_identity_not_seen_in_a_while"  # good


log = logging.getLogger(__name__)

# use the official ports only, don't go for the weird ports just yet :)
DEFAULT_FTP_PORTS = [21]
DEFAULT_HTTP_PORTS = [443, 80, 8443, 8080, 8000]
DEFAULT_IMAP4_PORTS = [993, 143]
DEFAULT_POP3_PORTS = [110, 995]
DEFAULT_SMTP_PORTS = [25, 587, 465, 3535]
DEFAULT_SSH_PORTS = [22]
DEFAULT_SMB_PORTS = [445]
DEFAULT_TELNET_PORTS = [23, 992]  # 107?
DEFAULT_RDP_PORTS = [3389]
DEFAULT_VNC_PORTS = [5500]

# todo: perhaps this should be a little more relaxed / split up into separate scans to avoid being blocked by a firewall
STANDARD_PORTS = (
    DEFAULT_FTP_PORTS
    + DEFAULT_HTTP_PORTS
    + DEFAULT_IMAP4_PORTS
    + DEFAULT_POP3_PORTS
    + DEFAULT_SMTP_PORTS
    + DEFAULT_SSH_PORTS
    + DEFAULT_SMB_PORTS
    + DEFAULT_TELNET_PORTS
    + DEFAULT_RDP_PORTS
    + DEFAULT_VNC_PORTS
)

DEFAULT_SSL_PORTS = []  # not used, because of weird ports, and there is a lot of ssl


def compose_scan_task(urls):
    return group([grab_banners.s()])


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    return compose_scan_task(grab_banners.s())


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def grab_banners():

    if not allowed_to_scan(SCANNER_NAME):
        return

    # depending on v4 or v6 you need to specify the source address.
    grab_banners_ip_version(constance_cached_value("BANNERGRAB_IPV4_LISTEN_IP"), True)
    grab_banners_ip_version(constance_cached_value("BANNERGRAB_IPV6_LISTEN_IP"), False)


def grab_banners_ip_version(listen_ip: str, is_v4: bool = True):

    if not listen_ip:
        log.error("Cannot listen to returned packets without a listen ip. Configure one or disable this scanner.")
        return

    v4_targets = ",".join(UrlIp.objects.all().filter(is_unused=False, is_v4=is_v4).values_list("ip", flat=True))
    mas = masscan.PortScanner()
    ports = ",".join(str(x) for x in STANDARD_PORTS)
    output = mas.scan(v4_targets, ports=ports, arguments=f"--banners --max-rate 100 --source-ip {listen_ip}")
    handle_masscan_output(output)


def handle_masscan_output(output):
    """
    {
        "command_line": "masscan -oJ - 192.168.1.1 -p 80,1900",
        "scan": {
            "93.93.121.93": [
                {
                    "port": 80,
                    "proto": "tcp",
                    "status": "open",
                    "reason": "syn-ack",
                    "ttl": 244
                },
                {
                    "port": 443,
                    "proto": "tcp",
                    "service": {
                        "name": "ssl",
                        "banner": " ALERT(0x0228) "
                    }
                }
            ],
            "213.222.0.119": [
                {
                    "port": 8443,
                    "proto": "tcp",
                    "status": "open",
                    "reason": "syn-ack",
                    "ttl": 56
                },
    """

    for ip, rows in output["scan"].items():
        for row in rows:
            if "service" in row:
                service_banner = row["service"]["banner"]
                service_name = row["service"]["name"]
                process_result(ip, row["port"], service_name, service_banner)

    clean_old_bannergrab_results()


def process_result(ip, port, service_name, banner):
    # some cert info.
    # X509 is handled by qualys
    if service_name in ["X509", "ssl"]:
        return

    # in many cases the http is just a http response with a server banner in it.
    # The server banner can be grabbed from http.server
    if service_name in ["http"]:
        return

    if service_name in ["title"]:
        return

    conclusion = detect_a_likely_version(banner, "http")

    protocol = masscan_service_name_to_protocol(service_name)

    # get the urls that have this IP. And are up to date etc...
    for url in get_urls_by_ip(ip):
        # you know the urls based ip.
        log.error(url.url)
        endpoint = Endpoint.force_get(url_id=url.url.id, port=port, protocol=protocol, ip_version=6 if ":" in ip else 4)

        store_endpoint_scan_result(
            scan_type=SCANNER_NAME, endpoint_id=endpoint.id, rating=conclusion, evidence=banner, message=""
        )


def masscan_service_name_to_protocol(service_name):
    service_name = service_name.lower()

    if service_name == "http.server":
        return "http"

    return service_name


def get_urls_by_ip(ip):
    return UrlIp.objects.all().filter(ip=ip).only("id", "url", "url__id")


def clean_old_bannergrab_results():
    #  connect the finding to the urls that have this IP, this can be a lot of urls
    #  Things that have not seen for a while will be deleted. EndpointGenericScan of this type older than 7 days
    # means that it has not been seen. All the other values are auto-update etc. The amount of days depends on how
    # many times this scan is run. The data is not really stable. Probably is a lot blocks ands such. If it's blocked
    # then so be it. Might not be blocked after a day or two...
    old_scans = datetime.now(pytz.utc) - timedelta(days=constance_cached_value("BANNERGRAB_DAYS_TO_OUTDATED_METRIC"))
    old_epgs = EndpointGenericScan.objects.all().filter(type=SCANNER_NAME, last_scan_moment__lte=old_scans)

    # When there's new stuff it will show up automatically
    for old_epg in old_epgs:
        store_endpoint_scan_result(
            scan_type=SCANNER_NAME,
            endpoint_id=old_epg.endpoint.id,
            rating=SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE,
            evidence="",
            message="",
        )

    # How do you know if the endpoint still exists? It will have no data attached to it when there is no
    # issue, so that will not be shown. Not an issue.


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
