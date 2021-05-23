from celery import group

from websecmap.celery import app
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import get_relevant_microsoft_domains_from_database
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner import unique_and_random
from websecmap.scanners.scanner.autoexplain_trust_microsoft import (
    autoexplain_trust_microsoft_and_include_their_webserver_headers,
)


SCANNER = "autoexplain_microsoft_neighboring_services"

query = EndpointGenericScan.objects.all().filter(
    comply_or_explain_explanation="trusted_on_local_device_with_custom_trust_policy",
    comply_or_explain_is_explained=True,
    is_the_latest_scan=True,
    endpoint__protocol="https",
    endpoint__is_dead=False,
    rating="not trusted",
)


@app.task(queue="storage")
def plan_scan():
    scans = query.filter(endpoint__url__in=get_relevant_microsoft_domains_from_database())
    urls = [endpoint_generic_scan.endpoint.url.pk for endpoint_generic_scan in scans]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    return group(
        [
            scan.si(scan_id=endpoint_generic_scan.pk)
            | plannedscan.finish.si("scan", SCANNER, endpoint_generic_scan.endpoint.url.pk)
            for endpoint_generic_scan in list(set(query.filter(endpoint__url__in=urls)))
        ]
    )


@app.task(queue="storage")
def scan(scan_id: int):
    """
    Some domains in the database have an automatic explanation, but are missing the header explanations.
    Add those automatically. For example when the headers are found _after_ the tls scan is performed.
    """

    scan = EndpointGenericScan.objects.all().filter(id=scan_id)
    if not scan:
        return

    # assuming the explanation is unique, which it probably isn't
    autoexplain_trust_microsoft_and_include_their_webserver_headers(scan)
