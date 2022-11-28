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


from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import Endpoint, UrlIp
from websecmap.scanners.scanmanager import store_endpoint_scan_result
import logging

from celery import Task, group

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.scanners import init_dict
from websecmap.scanners.scanner.__init__ import (
    allowed_to_scan,
)
import masscan

from websecmap.scanners.scanner.banners.detect_version import detect_a_likely_version
from websecmap.scanners.scanner.banners.utils import clean_old_bannergrab_results, get_urls_by_ip

SCANNER_NAME = "bannergrab_masscan"


log = logging.getLogger(__name__)


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

    clean_old_bannergrab_results()


def grab_banners_ip_version(listen_ip: str, is_v4: bool = True):

    if not listen_ip:
        log.error("Cannot listen to returned packets without a listen ip. Configure one or disable this scanner.")
        return

    v4_targets = ",".join(UrlIp.objects.all().filter(is_unused=False, is_v4=is_v4).values_list("ip", flat=True))
    mas = masscan.PortScanner()
    ports = ",".join(str(x) for x in constance_cached_value("BANNERGRAB_STANDARD_PORTS").split(","))
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
        endpoint = Endpoint.force_get(url_id=url.url.id, port=port, protocol=protocol, ip_version=6 if ":" in ip else 4)

        store_endpoint_scan_result(
            scan_type=SCANNER_NAME, endpoint_id=endpoint.id, rating=conclusion, evidence=banner, message=""
        )


def masscan_service_name_to_protocol(service_name):
    service_name = service_name.lower()

    if service_name == "http.server":
        return "http"

    return service_name
