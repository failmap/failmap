import contextlib
from json import JSONDecodeError
from typing import Optional
import json

from celery import group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import DomainIp, EndpointGenericScan, DomainMX
from websecmap.scanners.scanner.http import get_ipv4, get_ipv6
from websecmap.scanners.scanner.web_privacy import WEB_PRIVACY_THIRD_PARTY_DOMAINS
from websecmap.scanners.time_storage import abstract_time_storage
import tldextract


@app.task(queue="kickoff")
def create_tasks() -> group:
    return group(
        [
            add_domains_from_organization_urls(),
            add_domains_from_privacy_scan(),
            add_domains_from_mailserver_records(),
        ]
    )


def add_domains_from_mailserver_records() -> group:
    domains = set()
    for list_of_domains in DomainMX.objects.all().filter(is_the_latest=True):
        if list_of_domains.mail_server_records:
            mail_server_records = list_of_domains.mail_server_records
            for mail_server_record in mail_server_records:
                # todo: should not be an ip address. should be an fqdn.
                if mail_server_record["domain"]:
                    extract = tldextract.extract(mail_server_record["domain"])
                    if extract.fqdn:
                        domains.add(extract.fqdn)
    return group([update_ips(domain) for domain in list(domains)])


def add_domains_from_privacy_scan() -> group:
    # combine lists of external requests. There will be many, but the amount of different domains will be few.
    domains = set()
    for list_of_domains in EndpointGenericScan.objects.all().filter(
        type=WEB_PRIVACY_THIRD_PARTY_DOMAINS, is_the_latest_scan=True
    ):
        with contextlib.suppress(JSONDecodeError):
            evidence = json.loads(list_of_domains.evidence)
            domains.update(evidence)
    return group([update_ips(domain) for domain in list(domains)])


def add_domains_from_organization_urls() -> group:
    return group(
        [update_ips(url.url) for url in Url.objects.all().filter(is_dead=False, not_resolvable=False).only("url")]
    )


def update_ips(domain: str):
    return group(get_ipv4.si(domain) | store_ip.s(domain, 4) | get_ipv6.si(domain) | store_ip.s(domain, 6))


@app.task(queue="storage", ignore_result=True)
def store_ip(ip: Optional[str], domain: str, ip_version: int):
    # take into account the by-design limitation of the length of a domain, for now. If there are many
    # longer domains incl subdomains, then change the data type to a very long type.
    data = {"ip_address": ip or None, "domain": domain[:255], "ip_version": ip_version}

    # don't store useless data, only store an empty ip if there was an ip in the past
    if not ip and not DomainIp.objects.filter(domain=domain, ip_version=ip_version).exists():
        return

    abstract_time_storage(
        DomainIp,
        fields_to_retrieve_latest={"domain": domain, "ip_version": ip_version},
        fields_that_signify_change=["ip_address"],
        data_for_new_record=data,
    )
