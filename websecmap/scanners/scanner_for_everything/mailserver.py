# tries to find a mailserver attached to a domain
# https://mxtoolbox.com/SuperTool.aspx?action=aaaa%3agoogle.com&run=toolpage
# https://stackoverflow.com/questions/9463086/how-to-do-dns-aaaa-cname-and-srv-lookups-in-c
# todo: should we just add all dns records?
from typing import Optional, List

from celery import group

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import DomainMX
from websecmap.scanners.scanner.dns_endpoints import get_dns_records
from websecmap.scanners.time_storage import abstract_time_storage


@app.task(queue="kickoff")
def create_tasks() -> group:
    tasks = group([get_mailservers.si(url.url) | store_mailserver.s(url.url) for url in Url.objects.all()])
    tasks.apply_async()
    return group([])


@app.task(queue="database", ignore_result=True)
def get_mailservers(url: str) -> List:
    answer = get_dns_records(url, "MX")
    if not answer:
        return []

    # https://github.com/internetstandards/Internet.nl-dashboard/issues/525
    if answer is True:
        return []

    # transform the rrset to something we can work with (a bit)
    # this saves the "oh, the prio 40 record is gone, check if we had that etc etc" by making it a simple list
    records = []
    for record in answer:
        mail_domain = record.exchange.to_text()
        mail_prio = record._processing_priority()
        # strip the trailing dot of the mail domain:
        mail_domain = mail_domain[:-1] if mail_domain.endswith(".") else mail_domain

        # don't add empty domains. In fact everything can be terrible here, but assume it's not?
        if mail_domain:
            records.append({"priority": mail_prio, "domain": mail_domain})

    return records


@app.task(queue="storage", ignore_result=True)
def store_mailserver(mail_server_records: Optional[str], domain: str):
    data = {"mail_server_records": mail_server_records or None, "domain": domain[:255]}

    # only store empty records if there was a previous mail server. Don't store empty records as that is a waste of
    # space.
    if not mail_server_records and not DomainMX.objects.filter(domain=domain).count():
        log.debug("No mail server records found for domain %s", domain)
        return

    abstract_time_storage(
        DomainMX,
        fields_to_retrieve_latest={"domain": domain},
        fields_that_signify_change=["mail_server_records"],
        data_for_new_record=data,
    )
