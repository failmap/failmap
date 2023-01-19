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

from websecmap.scanners.scanner.banners.detect_version import detect_a_likely_version, clean_banner
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


@app.task(queue="storage", ignore_result=True)
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

    banner = clean_banner(banner, "http")
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
