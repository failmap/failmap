"""
Retrieves IP addresses for several ip-based scans. These are stored in the UrlIp table.
"""
import logging
from datetime import datetime, timezone

from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict
from websecmap.scanners.models import UrlIp
from websecmap.scanners.scanner.__init__ import allowed_to_scan
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


@app.task(queue="storage")
def refresh_ips():
    # find ip-addresses from all domains currently used. This is currently not in the database.
    # this takes a larger amount of dns queries.

    # reduce the list of ip's to unique ones and connect the domains that use them to it. Save that in the db anyway
    # in the urlip table.

    # this is done linearly: it could be done with a threadpool, but this is already very fast... so why bother to
    # overload the resolver. That would not be nice :)
    if not allowed_to_scan(SCANNER_NAME):
        return

    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False).only("id", "url")

    for url in urls:
        ipv4 = get_ipv4(url.url)
        if ipv4:
            store_ip(url, True, ipv4)
        else:
            clean_ips(url, True)

        ipv6 = get_ipv6(url.url)
        if ipv6:
            store_ip(url, False, ipv6)
        else:
            clean_ips(url, False)


def clean_ips(url: Url, is_v4: bool):
    url_ips = UrlIp.objects.all().filter(url=url, is_v4=is_v4, is_unused=False)
    for url_ip in url_ips:
        unuse_url_ip(url_ip, "no ip found anymore")


def store_ip(url: Url, is_v4: bool, ip: str):
    has_ip = UrlIp.objects.all().filter(url=url, is_v4=is_v4, ip=ip).first()
    if has_ip:
        log.debug("Url: %s, ip: %s, is_v4: %s is already in the database: cleaning.", url, is_v4, ip)

        # revive it, but remove the others
        if has_ip.is_unused:
            log.debug("Url: %s, ip: %s, is_v4: %s is has been revived.", url, is_v4, ip)
            has_ip.is_unused = False
            has_ip.save()

    else:
        log.debug("Url: %s, ip: %s, is_v4: %s has been added to the db as first ip for this url.", url, is_v4, ip)
        UrlIp.objects.create(url=url, is_v4=is_v4, ip=ip, discovered_on=datetime.now(timezone.utc))

    # clean up the rest
    to_unuse = UrlIp.objects.all().filter(url=url, is_v4=is_v4).exclude(ip=ip)
    for url_ip in to_unuse:
        log.debug("Url: %s, ip: %s, is_v4: %s is made unavailable.", url, is_v4, ip)
        unuse_url_ip(url_ip, "found alternative ip")


def unuse_url_ip(url_ip: UrlIp, reason: str = "found alternative ip"):
    url_ip.is_unused = True
    url_ip.is_unused_since = datetime.now(timezone.utc)
    url_ip.is_unused_reason = reason
    url_ip.save()
