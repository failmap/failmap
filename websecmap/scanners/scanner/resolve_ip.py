"""
Retrieves IP addresses for several ip-based scans. These are stored in the UrlIp table.
"""
import logging
from datetime import datetime, timezone
from typing import List

from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict
from websecmap.scanners.models import UrlIp
from websecmap.scanners.scanner.__init__ import allowed_to_scan
from websecmap.scanners.scanner.dns_endpoints import get_ips_from_dns
from websecmap.scanners.scanner.http import get_ipv4, get_ipv6

SCANNER_NAME = "resolve_ip"

log = logging.getLogger(__name__)


def compose_scan_task(urls):
    return group([refresh_ips.s()])


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    return compose_scan_task(refresh_ips.s())


@app.task(queue="database")
def refresh_ips():
    # todo: there will mostly be more than one A/AAAA record in the DNS and one is supplied at random. We should
    #  get all those records and from there see if the retrieved ones matches the one in the database. If so then
    #  we don't need to update anything. We currently act like there is only one ip per server, which is fine as long
    #  as it resolved. But current practices makes the urlip table longer than needed.

    # find ip-addresses from all domains currently used. This is currently not in the database.
    # this takes a larger amount of dns queries.

    # reduce the list of ip's to unique ones and connect the domains that use them to it. Save that in the db anyway
    # in the urlip table.

    # this is done linearly: it could be done with a threadpool, but this is already very fast... so why bother to
    # overload the resolver. That would not be nice :)

    # TODO: this needs to be refactored to chunk the urls, as it can currently take hours for one run to finish
    if not allowed_to_scan(SCANNER_NAME):
        return

    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False).only("id", "url")

    tasks = [refresh_ips_from_url.si(url.id) for url in urls]
    tasks = group(tasks)
    tasks.apply_async()


@app.task(queue="database")
def refresh_ips_from_url(url_id):
    url = Url.objects.all().filter(id=url_id, is_dead=False, not_resolvable=False).only("id", "url").first()
    if not url:
        return

    # performing 4 requests:
    ips_in_dns = get_ips_from_dns(url.url, "A")
    if ipv4 := get_ipv4(url.url):
        store_ip(url, is_v4=True, ip=ipv4, ips_in_dns=ips_in_dns)
    else:
        clean_ips(url, is_v4=True)

    ips_in_dns = get_ips_from_dns(url.url, "AAAA")
    if ipv6 := get_ipv6(url.url):
        store_ip(url, is_v4=False, ip=ipv6, ips_in_dns=ips_in_dns)
    else:
        clean_ips(url, is_v4=False)


def clean_ips(url: Url, is_v4: bool):
    url_ips = UrlIp.objects.all().filter(url=url, is_v4=is_v4, is_unused=False)
    for url_ip in url_ips:
        unuse_url_ip(url_ip, "no ip found anymore")


def store_ip(url: Url, is_v4: bool, ip: str, ips_in_dns: List[str]):
    # IP: one of the ip's retrieved, which is one retrieved from the DNS in a round robin fashion
    # ips_in_dns: most ip's retrieved from the DNS. But this might be a subset still in case of high
    #  volume domains. Or behind 'cloudflare' things etc...
    has_ip = UrlIp.objects.all().filter(url=url, is_v4=is_v4, ip__in=ips_in_dns).first()
    if has_ip:
        log.debug("Known IP: %s", has_ip.ip)
    log.debug("Received IP: %s", ip)
    log.debug("Received IP from dns: %s", ips_in_dns)

    if has_ip and has_ip.ip in ips_in_dns:
        log.debug(
            "Url: %s, ip: %s, is_v4: %s is already in the database as ip %s: cleaning.", url, is_v4, ip, has_ip.ip
        )

        # revive it, but remove the others
        if has_ip.is_unused:
            log.debug("Url: %s, ip: %s, is_v4: %s is has been revived.", url, is_v4, ip)
            has_ip.is_unused = False
            has_ip.save()

    else:
        log.debug("Url: %s, ip: %s, is_v4: %s has been added to the db as first ip for this url.", url, is_v4, ip)
        UrlIp.objects.create(url=url, is_v4=is_v4, ip=ip, discovered_on=datetime.now(timezone.utc))

    # clean up the rest
    to_unuse = UrlIp.objects.all().filter(url=url, is_v4=is_v4).exclude(ip__in=ips_in_dns)
    for url_ip in to_unuse:
        log.debug("Url: %s, ip: %s, is_v4: %s is made unavailable.", url, is_v4, url_ip.ip)
        unuse_url_ip(url_ip, "found alternative ip")


def unuse_url_ip(url_ip: UrlIp, reason: str = "found alternative ip"):
    url_ip.is_unused = True
    url_ip.is_unused_since = datetime.now(timezone.utc)
    url_ip.is_unused_reason = reason
    url_ip.save()
