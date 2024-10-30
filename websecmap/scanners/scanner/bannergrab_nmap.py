"""
Grabs banners (software versions) from a series of protocols. Filters them and adds them to findings.

This prevents attackers to find a simple version and monitor that until an exploit comes available. An
attacker has to put in more work. This is public information published by organizations. Let's hope
they use fake banners, that's much more fun :)
"""

import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import nmap

from celery import Signature, group

from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.scanners import init_dict
from websecmap.scanners.scanner.http import get_endpoint, force_get_endpoint, get_ipv4, kill_endpoint, get_ipv6
from websecmap.scanners.models import EndpointGenericScan, UrlIp, Endpoint
from websecmap.scanners.scanmanager import endpoint_has_scans, store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, unique_and_random
from websecmap.scanners.scanner.banners.detect_version import (
    SERVICE_IDENTITY_NO_BANNER_FOUND,
    clean_banner,
    detect_a_likely_version,
)
from websecmap.scanners.scanner.banners.utils import get_urls_by_ip
from websecmap.scanners.scanner.utils import in_chunks

SCANNER_NAME = "bannergrab_nmap"
IPS_PER_SCAN = 100

# tcpwrapped means no response
SUPPORTED_PROTOCOLS = {"http", "https", "ssh"}

log = logging.getLogger(__name__)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> list[Signature]:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    if organizations_filter or endpoints_filter:
        raise NotImplementedError("Organization or endpoints filter not supported")

    if not allowed_to_scan(SCANNER_NAME):
        return group()

    return group(grab_tasks(urls_filter=urls_filter))


@app.task(queue="storage", ignore_result=True)
def grab_banners():
    if not allowed_to_scan(SCANNER_NAME):
        return

    group(grab_tasks()).apply_async()


def get_all_ip_addresses(is_v4=True, urls_filter=None):
    urls = UrlIp.objects.all()
    if urls_filter:
        urls_filter = {k.replace("url__iregex", "url__url__iregex"): v for k, v in urls_filter.items()}
        urls = urls.filter(**urls_filter)
    ip_addresses = urls.filter(is_unused=False, is_v4=is_v4).values_list("ip", flat=True)
    return list(ip_addresses)


def get_ips_to_be_scanned(is_v4, urls_filter=None) -> List[str]:
    ips = get_all_ip_addresses(is_v4, urls_filter=urls_filter)
    # randomize the order to distribute load of scans
    return unique_and_random(ips)


def get_ports_to_be_scanned() -> str:
    return ",".join(str(x) for x in constance_cached_value("BANNERGRAB_STANDARD_PORTS").split(","))


def grab_tasks(urls_filter=None) -> list[Signature]:
    hosts_per_scan = IPS_PER_SCAN

    ports = get_ports_to_be_scanned()
    tasks = []

    ipv4_ips = get_ips_to_be_scanned(is_v4=True, urls_filter=urls_filter)
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
    # T4 results in tcpwrapped responses too much it seems, so slow down and go to T3 instead of T4.
    nm.scan(ip_argument, ports, arguments="-sV --host-timeout=5m -T3 --script=banner")
    log.debug("command line: %s", nm.command_line())
    log.debug("scaninfo: %s", nm.scaninfo())
    return nm


@app.task(queue="bannergrab")
def grab_task(ips: List[str], ports: str):
    nm = start_scanner(ips, ports)
    return {host: nm[host] for host in nm.all_hosts()}


@app.task(queue="storage", ignore_result=True)
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


def reduce_protocol(protocol, port):
    # we've found that fingerprinting is sometimes unreliable and in 99.99% of cases it's just
    # https or http where it says otherwise. It's a flavor thing perhaps.
    # nmap is great, but in this case we can safely assume just http/https.

    if int(port) in {80}:
        return "http"

        # mapping = {
        #     "http-proxy": "http",
        #     "gnutella": "http",
        #     "ms-wbt-server": "http",
        #     "upnp": "http",
        #     "sip": "http",
        # }
        # protocol = mapping.get(protocol, protocol)

    if int(port) in {443, 8443}:
        return "https"
        # make sure this in sync with PROTOCOL_CLEANERS in detect_version
        # mapping = {
        #     # http on 443 happens a lot, and while technically correct place it on 443 anyway
        #     "http": "https",
        #     "http-proxy": "https",
        #     "ssl/http": "https",
        #     "ssl": "https",
        #     "ssl/http-proxy": "https",
        #     # this is always a misclassification
        #     "gnutella": "https",
        #     "ms-wbt-server": "https",
        #     "upnp": "https",
        #     "sip": "https",
        # }
        # protocol = mapping.get(protocol, protocol)

    return str(protocol).strip().lower()


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
    # todo: there are hosts missing from the input lists, those endpoints should be set to dead.
    #  this is now worked around in verify().

    log.info("processing nmap scan result on %s:%s results: %s", ip, port, result)

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
    protocol = result.get("name", "http")

    # tcpwrapped happens when a server drops a connection. In this case it is not clear what
    # protocol is answering in the standard port. Do not store this as a separate protocol result.
    # Tcpwrapped means there will be no data returned and no banner...
    # If this happens too much the intensity of scans needs to be reduced.
    # happens so often we don't want to flood the logs. Don't log it as it happens all the time.
    if protocol == "tcpwrapped":
        return

    # make some assumptions about the protocol in use, override what nmap thinks in these cases.
    # the http/https would have been discovered by the http/https scanner.
    protocol = reduce_protocol(protocol, port)

    if protocol not in SUPPORTED_PROTOCOLS:
        log.error("Unsupported protocol: %s", protocol)
        return

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

        # reducing the protocol _again_ as it seems to be reset to an old value http-proxy,
        # while we cannot possibly reproduce this. While http-proxy endpoints keep on being added while the
        # protocol has already been reduced. This makes the variable a bit more local.

        # nmap correctly finds that it is HTTP over port 443, not https over 443, and every time those http/443 sites
        # will tell us to use the https version of the site. To prevent creating infinite useless endpoints
        # silently upgrade the http results to https. We see all of those disappear over time.
        # nmap results appear to be a string, and therefore the protocol is not upgraded to https in this
        # specific scenario.
        if protocol == "http" and port in {443, "443", 8443, "8443"}:
            protocol = "https"

        # for SSH this scanner is in control, so ssh can be _force_get, the rest is only get.
        # because this scanner is in charge of SSH ports. Will also verify them in case they are not resolvable etc.
        # tie this to 22 as the verify is also tied to that still.
        if protocol == "ssh" and port == 22:
            endpoint = force_get_endpoint(
                url_id=url.url.id, port=port, protocol=protocol, ip_version=ip_version(ip), origin="bannergrab_nmap"
            )
        else:
            endpoint = get_endpoint(
                url_id=url.url.id, port=port, protocol=protocol, ip_version=ip_version(ip), origin="bannergrab_nmap"
            )

        if not endpoint:
            log.warning("No endpoint found for url: %s, port: %s, protocol: %s", url.url.id, port, protocol)
            continue

        # clean the banner if there was one in the past. Adds a banner if there is a new one / something has changed.
        if not banner and endpoint_has_scans("bannergrab", endpoint.id) or banner:
            evidence = f"found on {ip}, port {port}: {banner}"
            store_endpoint_scan_result(
                scan_type="bannergrab", endpoint_id=endpoint.id, rating=conclusion, evidence=evidence, message=banner
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


def get_ssh_scans():
    return EndpointGenericScan.objects.all().filter(
        type="bannergrab",
        last_scan_moment__lte=datetime.now(timezone.utc) - timedelta(days=5),
        is_the_latest_scan=True,
        endpoint__is_dead=False,
        endpoint__protocol="ssh",
    )


@app.task(queue="storage", ignore_result=True)
def verify():
    # The normal scanner does not remove non-existing endpoints. This is because ip's that cannot be scanned or
    # have no results are not in output of the all_hosts() command. Because of this mismatch very old endpoints
    # where present in the database and their (obsolete) metrics persisted in reports.

    # This code performs a verify on all hosts that have not had updated results for a while. It will do this in two
    # steps. The first is to just see if the ip resolves at all. If not, the endpoint is killed right away.
    # The second step will perform an ssh scan with NMAP to the specific host. If there is no output, the
    # endpoint is killed.

    # An example, extranet.poraad.nl, has an IP address but blocks traffic from unknown sources. This wasn't the case
    # when scanning started. Possibly the scan was blocked.

    # first pass, saves on NMAP scans, find all hosts that don't resolve anymore, these are easy to remove.
    # if there are no ip's for this host, mark these endpoints as dead.
    # otherwise they would have still been scanned and there would be no banner
    for scan in get_ssh_scans():
        endpoint = scan.endpoint
        if endpoint.ip_version == 4:
            ipv4 = get_ipv4(endpoint.url.url)
            if not ipv4:
                kill_endpoint(
                    endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_no_resolve"
                )
        if endpoint.ip_version == 6:
            ipv6 = get_ipv6(endpoint.url.url)
            if not ipv6:
                kill_endpoint(
                    endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_no_resolve"
                )

    # second pass: these hosts still resolve but do not have NMAP output. Because they are missing from the output
    # as only found hosts with results are in the output. So go over them one by one and kill the endpoint if there
    # is no output
    scans = get_ssh_scans()
    for scan in scans:
        (
            get_nmap_result_for_one_host.s(scan.endpoint.url.url, scan.endpoint.ip_version, str(scan.endpoint.port))
            | store_nmap_verification.s(scan.endpoint.id)
        ).apply_async()


@app.task(queue="bannergrab")
def get_nmap_result_for_one_host(url: str, ip_version: int, port: str):
    ip = get_ipv4(url) if ip_version == 4 else get_ipv6(url)
    results = start_scanner([ip], port)
    # make sure this is serializable by running all_hosts.
    hosts = results.all_hosts()
    log.debug("Found %s hosts for %s", len(hosts), url)
    return results[hosts[0]] if hosts else ""


@app.task(queue="storage", ignore_result=True)
def store_nmap_verification(output, endpoint_id: int):
    endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    if not endpoint:
        return

    # host seems down
    if not output:
        kill_endpoint(endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_out")

    # filtered host or something else?
    """
    output['185.84.143.112']
    {
      'hostnames': [
        {
          'name': '',
          'type': ''
        }
      ],
      'addresses': {
        'ipv4': '185.84.143.112'
      },
      'vendor': {},
      'status': {
        'state': 'up',
        'reason': 'syn-ack'
      },
      'tcp': {
        22: {
          'state': 'filtered',
          'reason': 'no-response',
          'name': 'ssh',
          'product': '',
          'version': '',
          'extrainfo': '',
          'conf': '3',
          'cpe': ''
        }
      }
    }
    """
    if "tcp" not in output:
        kill_endpoint(endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_no_tcp")
        return

    # note that ports are a string.
    # use a separate source message in case this ever changes to an int.
    # this SHOULD be ssh, not port 22, this ties the ssh scans to this specific port...
    # there could be multiple ports as well, so this isn't really nicely designed.
    if "22" not in output["tcp"]:
        kill_endpoint(endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_no_22")
        return

    # only open is fine.
    # https://nmap.org/book/man-port-scanning-basics.html
    if output["tcp"]["22"]["state"] in ["filtered", "closed", "open|filtered", "closed|filtered"]:
        kill_endpoint(
            endpoint.protocol, endpoint.url.id, endpoint.port, endpoint.ip_version, "bannergrab_nmap_not_open"
        )
