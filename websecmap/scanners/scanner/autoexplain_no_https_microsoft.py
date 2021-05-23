import logging
from datetime import timedelta

from celery import group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan
import dns

from websecmap.scanners.scanner import unique_and_random

log = logging.getLogger(__package__)


SCANNER = "autoexplain_no_https_microsoft"
EXPLANATION = "service_intentionally_designed_this_way"

query = EndpointGenericScan.objects.all().filter(
    type="plain_https",
    is_the_latest_scan=True,
    comply_or_explain_is_explained=False,
    endpoint__is_dead=False,
    endpoint__protocol="http",
    endpoint__port=80,
    rating="25",
)


@app.task(queue="storage")
def plan_scan():
    # Only check this on the latest scans, do not alter existing explanations
    scans = query.filter(
        endpoint__url__in=Url.objects.all().filter(
            computed_subdomain="autodiscover", not_resolvable=False, is_dead=False
        )
    )

    urls = [endpoint_generic_scan.endpoint.url.pk for endpoint_generic_scan in scans]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    scans = query.filter(endpoint__url__in=urls)

    tasks = [
        scan.si(scan_id=endpoint_generic_scan.pk)
        | plannedscan.finish.si("scan", SCANNER, endpoint_generic_scan.endpoint.url.pk)
        for endpoint_generic_scan in list(set(scans))
    ]

    return group(tasks)


@app.task(queue="storage")
def scan(scan_id):
    # todo: break scan into smaller pieces to not interrupt the storage queue

    """
    Microsoft Office365/Exchange need the autodiscover subdomain. This is configured as a CNAME. The CNAME
    cannot be further configured. Microsoft does not expose an HTTPS service over this subdomain, only http.
    This is true for the "online" configuration, not for the "on premise" configuration.
    The documentation on "WHY IS THIS SECURE" is not really well done (or at least microsoft style obfuscated).
    Currently we "assume" that they know what they are doing, since they have a well performing security team.
    issue: https://gitlab.com/internet-cleanup-foundation/web-security-map/-/issues/271

    The CNAME will point to autodiscover.outlook.com. Thus in that case we can quickly validate that this specific
    issue will always be the same.
    """

    endpoint_generic_scan = EndpointGenericScan.objects.all().filter(id=scan_id)
    if not endpoint_generic_scan:
        return

    try:
        result = dns.resolver.query(endpoint_generic_scan.endpoint.url.url, "CNAME")
        for cnameval in result:
            # don't accept trickery such as autodiscover.outlook.com.mydomain.com.
            log.debug(f"Retrieved cname value: {cnameval}.")
            if "autodiscover.outlook.com." == str(cnameval):
                log.debug("Perfect match, will add automatic explanation.")
                add_bot_explanation(endpoint_generic_scan, EXPLANATION, timedelta(days=365 * 10))
    except dns.exception.DNSException as e:
        log.debug(f"Received an expectable error from dns server: {e}.")
        # can happen of course.
        # sample: dns.resolver.NXDOMAIN, dns.exception.Timeout, dns.resolver.NoAnswer, dns.query.BadResponse
