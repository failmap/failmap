"""
Grabs banners (software versions) from a series of protocols. Filters them and adds them to findings.

This prevents attackers to find a simple version and monitor that until an exploit comes available. An
attacker has to put in more work. This is public information published by organizations. Let's hope
they use fake banners, that's much more fun :)
"""

import contextlib
from typing import Dict, Any, List

from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import UrlIp, Endpoint, EndpointGenericScan
from websecmap.scanners.scanmanager import store_endpoint_scan_result, endpoint_has_scans
import logging

from celery import Task, group

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.scanners import init_dict
from websecmap.scanners.scanner.__init__ import (
    allowed_to_scan,
    unique_and_random,
)
import nmap

from websecmap.scanners.scanner.banners.detect_version import (
    detect_a_likely_version,
    SERVICE_IDENTITY_NO_BANNER_FOUND,
    clean_banner,
)
from websecmap.scanners.scanner.banners.utils import get_urls_by_ip
from websecmap.scanners.scanner.utils import in_chunks

SCANNER_NAME = "bannergrab_nmap"
IPS_PER_SCAN = 100

log = logging.getLogger(__name__)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    return group(grab_tasks())


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def grab_banners():

    if not allowed_to_scan(SCANNER_NAME):
        return

    group(grab_tasks()).apply_async()

    return


def get_all_ip_addresses(is_v4=True):
    return list(UrlIp.objects.all().filter(is_unused=False, is_v4=is_v4).values_list("ip", flat=True))


def get_ips_to_be_scanned(is_v4) -> List[str]:
    ips = get_all_ip_addresses(is_v4)
    # randomize the order to distribute load of scans
    return unique_and_random(ips)


def get_ports_to_be_scanned() -> str:
    return ",".join(str(x) for x in constance_cached_value("BANNERGRAB_STANDARD_PORTS").split(","))


def grab_tasks():
    hosts_per_scan = IPS_PER_SCAN

    ports = get_ports_to_be_scanned()
    tasks = []

    ipv4_ips = get_ips_to_be_scanned(is_v4=True)
    ipv4_chunks = in_chunks(ipv4_ips, hosts_per_scan)
    tasks += [grab_task.si(chunk, ports) | store_results_task.s() for chunk in ipv4_chunks]

    ipv6_ips = get_ips_to_be_scanned(is_v4=False)
    ipv6_chunks = in_chunks(ipv6_ips, hosts_per_scan)
    tasks += [grab_task.si(chunk, ports) | store_results_task.s() for chunk in ipv6_chunks]

    log.debug(f"Created {len(tasks)} bannergrab_nmap tasks.")

    return tasks


def start_scanner(ips, ports):
    log.debug(f"Starting nmap scanner on {len(ips)} ips, on ports {ports}.")

    # targets is space separated
    # ports is comma separated
    ip_argument = " ".join(ips)
    nm = nmap.PortScanner()
    # -sV: Probe open ports to determine service/version info
    # -v: Increase verbosity level (use -vv or more for greater effect)
    # --script banner: https://nmap.org/nsedoc/scripts/banner.html
    # "If you are on a decent broadband or ethernet connection, I would recommend always using -T4" = aggressive
    nm.scan(ip_argument, ports, arguments="-sV --host-timeout=5m -T aggressive --script=banner")
    log.debug(nm.command_line())
    log.debug(nm.scaninfo())
    return nm


@app.task(queue="bannergrab", expires=EXPIRES_IN_ONE_DAY)
def grab_task(ips: List[str], ports: str):
    nm = start_scanner(ips, ports)
    return {host: nm[host] for host in nm.all_hosts()}


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def store_results_task(results):
    # results are a dict of ip and results.
    log.debug("Storing results of nmap scan task.")

    for host, result in results.items():
        store_results(host, result)


def grab_manually(is_v4: bool = True):
    # can be used for inspection from the command line
    ips = get_ips_to_be_scanned(is_v4)
    ports = get_ports_to_be_scanned()
    log.debug(f"Going to scan {len(ips)} ips in batches of {IPS_PER_SCAN}.")
    chunks = in_chunks(ips, IPS_PER_SCAN)
    # could reuse the nm object
    for chunk in chunks:
        nm = start_scanner(chunk, ports)
        for host in nm.all_hosts():
            store_results(host, nm[host])


def reduce_protcol(protocol):
    mapping = {"http-proxy": "http"}

    return mapping.get(protocol, protocol)


def store_results(host, scan_result):
    log.debug("Store scan results for %s", host)
    """

    '185.71.61.127': {
          'hostnames': [
            {
              'name': 'basisbeveiliging.nl',
              'type': 'user'
            },
            {
              'name': 'basisbevprod01.cobytes.io',
              'type': 'PTR'
            }
          ],
          'addresses': {
            'ipv4': '185.71.61.127'
          },
          'vendor': {},
          'status': {
            'state': 'up',
            'reason': 'syn-ack'
          },
          'tcp': {
            22: {
              'state': 'open',
              'reason': 'syn-ack',
              'name': 'ssh',
              'product': 'OpenSSH',
              'version': '7.6p1 Ubuntu 4ubuntu0.5',
              'extrainfo': 'Ubuntu Linux; protocol 2.0',
              'conf': '10',
              'cpe': 'cpe:/o:linux:linux_kernel',
              'script': {
                'banner': 'SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5'
              }
            },
            80: {
              'state': 'open',
              'reason': 'syn-ack',
              'name': 'http',
              'product': 'nginx',
              'version': '',
              'extrainfo': '',
              'conf': '10',
              'cpe': 'cpe:/a:igor_sysoev:nginx'
            },
            443: {
              'state': 'open',
              'reason': 'syn-ack',
              'name': 'http',
              'product': 'nginx',
              'version': '',
              'extrainfo': '',
              'conf': '10',
              'cpe': 'cpe:/a:igor_sysoev:nginx'
            }
          }
        }

    {
      'nmap': {
        'command_line': 'nmap -oX - -p 22-443 -sV --script=banner -v6 basisbeveiliging.nl',
        'scaninfo': {
          'tcp': {
            'method': 'connect',
            'services': '22-443'
          }
        },
        'scanstats': {
          'timestr': 'Mon Nov 28 10:26:04 2022',
          'elapsed': '51.21',
          'uphosts': '1',
          'downhosts': '0',
          'totalhosts': '1'
        }
      },
      'scan': {
        ....
      }
    }
    """

    if "tcp" not in scan_result:
        clean_all_other_ports(host, [])
        return

    for port, result in scan_result["tcp"].items():
        process_result(host, port, result)

    do_not_clean_these_ports = [port for port, result in scan_result["tcp"].items() if result["state"] == "open"]
    clean_all_other_ports(host, do_not_clean_these_ports)


def get_banner_from_result(result) -> str:
    if "script" not in result:
        return ""

    # SSH banners
    banner = result["script"].get("banner", "")

    # HTTP server headers are in another output
    if not banner:
        banner = result["script"].get("http-server-header", "")

    # extra banners here...

    return banner


def ip_version(ip: str) -> int:
    return 6 if ":" in ip else 4


def process_result(ip: str, port: int, result: Dict[Any, Any]):
    log.debug("processing nmap scan result on %s:%s results: %s", ip, port, result)

    """
    Result:
    {
      'state': 'open',
      'reason': 'syn-ack',
      'name': 'ssh',
      'product': 'OpenSSH',
      'version': '7.6p1 Ubuntu 4ubuntu0.5',
      'extrainfo': 'Ubuntu Linux; protocol 2.0',
      'conf': '10',
      'cpe': 'cpe:/o:linux:linux_kernel',
      'script': {
        'banner': 'SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5'
      }
    }
    """
    protocol = reduce_protcol(result.get("name", "http"))

    with contextlib.suppress(ValueError):
        confidence = int(result["conf"])

    minimum_confidence = constance_cached_value("BANNERGRAB_PRODUCT_CONFIDENCE")
    log.debug("Confidence found: %s, minimum confidence needed: %s", confidence, minimum_confidence)

    product, version, extrainfo, cpe, banner = "", "", "", "", ""
    if confidence >= minimum_confidence:
        product = result["product"]
        version = result["version"]
        extrainfo = result["extrainfo"]
        cpe = result["cpe"]

    # get the banner from scripts, if there is no banner make one from the things that nmap is confident about
    banner = get_banner_from_result(result)
    if not banner and product:
        banner = f"{product} {version}" if version else product

    banner = clean_banner(banner, protocol)
    conclusion = detect_a_likely_version(banner, protocol)

    for url in get_urls_by_ip(ip):
        # todo: when are endpoints on random ports deleted? Or should we just remove old scan data for this scanner?
        endpoint = Endpoint.force_get(url_id=url.url.id, port=port, protocol=protocol, ip_version=ip_version(ip))

        # clean the banner if there was one in the past. Adds a banner if there is a new one / something has changed.
        if not banner and endpoint_has_scans("bannergrab", endpoint.id) or banner:
            store_endpoint_scan_result(
                scan_type="bannergrab", endpoint_id=endpoint.id, rating=conclusion, evidence=banner, message=banner
            )

        store_cpe_data(endpoint, "product_name", product)
        store_cpe_data(endpoint, "product_version", version)
        store_cpe_data(endpoint, "product_info", extrainfo)
        store_cpe_data(endpoint, "product_cpe", cpe)


def store_cpe_data(
    endpoint,
    data_item_name: str = "product_name",
    data_value: str = "",
):
    # only store an empty result if the information has gone.
    if not data_value and endpoint_has_scans(f"bannergrab_{data_item_name}", endpoint.id) or data_value:
        rating = f"{data_item_name}_neutral" if data_value else f"{data_item_name}_empty"
        store_endpoint_scan_result(
            scan_type=f"bannergrab_{data_item_name}",
            endpoint_id=endpoint.id,
            rating=rating,
            evidence=data_value,
            message=data_value,
        )


def clean_all_other_ports(host, do_not_clean_these_ports):
    # Data has been found on this host, but only for the ports included here. All other endpoints that are in the
    # database that have bannergrab data should be neutralized as that data is not found anymore.

    log.debug("Cleaning data on missing ports on host. Host %s, ports: %s", host, do_not_clean_these_ports)

    scan_types = [
        "bannergrab",
        "bannergrab_product_name",
        "bannergrab_product_version",
        "bannergrab_product_info",
        "bannergrab_product_cpe",
    ]

    scan_type_to_empty = {
        "bannergrab": SERVICE_IDENTITY_NO_BANNER_FOUND,
        "bannergrab_product_name": "product_name_empty",
        "bannergrab_product_version": "product_version_empty",
        "bannergrab_product_info": "product_info_empty",
        "bannergrab_product_cpe": "product_cpe_empty",
    }

    for url in get_urls_by_ip(host):

        # get the relevant endpoints.
        scans = (
            EndpointGenericScan.objects.all()
            .filter(
                type__in=scan_types,
                endpoint__url=url.url.id,
                is_the_latest_scan=True,
            )
            .exclude(endpoint__port__in=do_not_clean_these_ports)
        )

        log.debug("Found %s scans to remove data on.", scans.count())

        for scan in scans:

            # optimization:
            # do not attempt to store anything if the current result is already empty:
            if scan.rating == scan_type_to_empty.get(scan.type, ""):
                continue

            log.debug("Removing scan data on host %s, endpoint: %s, scan: %s", host, scan.endpoint, scan)
            store_endpoint_scan_result(
                scan_type=scan.type,
                endpoint_id=scan.endpoint.id,
                rating=scan_type_to_empty.get(scan.type, ""),
                evidence="",
                message="Port not found anymore.",
            )
