import logging
from datetime import timedelta

import dns
import requests
import tldextract
from celery import group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner import finish_those_that_wont_be_scanned, unique_and_random
from websecmap.scanners.scanner.autoexplain_trust_microsoft import (
    autoexplain_trust_microsoft_and_include_their_webserver_headers,
)

log = logging.getLogger(__package__)


SCANNER = "autoexplain_no_https_microsoft"
EXPLANATION = "service_intentionally_designed_this_way"

query = EndpointGenericScan.objects.all().filter(
    type="plain_http",
    is_the_latest_scan=True,
    comply_or_explain_is_explained=False,
    endpoint__is_dead=False,
    endpoint__protocol="http",
    endpoint__port=80,
    rating="https_redirect_on_insecure_port_and_no_https_on_standard_port",
)


@app.task(queue="kickoff", ignore_result=True)
def plan_scan():
    # Only check this on the latest scans, do not alter existing explanations
    scans = query.filter(
        endpoint__url__in=Url.objects.all().filter(
            computed_subdomain="autodiscover", not_resolvable=False, is_dead=False
        )
    )

    urls = [endpoint_generic_scan.endpoint.url for endpoint_generic_scan in scans]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    scans = query.filter(endpoint__url__in=urls)
    finish_those_that_wont_be_scanned(SCANNER, scans, urls)

    tasks = [
        scan.si(scan_id=endpoint_generic_scan.pk)
        | plannedscan.finish.si("scan", SCANNER, endpoint_generic_scan.endpoint.url.pk)
        for endpoint_generic_scan in list(set(scans))
    ]

    return group(tasks)


@app.task(queue="database", ignore_result=True)
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

    # don't try to explain scans that are already explained in the meanwhile(!) this task might be old and prior
    # tasks could already have explained this one.
    endpoint_generic_scan = (
        EndpointGenericScan.objects.all().filter(id=scan_id, comply_or_explain_is_explained=False).first()
    )
    if not endpoint_generic_scan:
        return

    # older services point to a cname
    if scan_over_network(endpoint_generic_scan.endpoint.url.url):
        add_bot_explanation(endpoint_generic_scan, EXPLANATION, timedelta(days=365 * 10))
        autoexplain_trust_microsoft_and_include_their_webserver_headers(endpoint_generic_scan)


def scan_over_network(domain_name_without_protocol: str) -> bool:
    return any(
        [
            insecure_site_redirects_to_microsoft(f"http://{domain_name_without_protocol}"),
            cname_redirect_to_microsoft(domain_name_without_protocol),
        ]
    )


def insecure_site_redirects_to_microsoft(url: str) -> bool:
    microsoft_login_urls = ["login.microsoftonline.com", "outlook.office365.com"]
    try:
        response = requests.head(url, verify=False, allow_redirects=True, timeout=10)
        extracted = tldextract.extract(response.url)
        return extracted.fqdn in microsoft_login_urls
    except requests.RequestException:
        log.debug("Does not redirect to Microsoft: %s", url)
        return False


def cname_redirect_to_microsoft(url: str) -> bool:
    try:
        result = dns.resolver.resolve(url, "CNAME")
        for cnameval in result:
            # don't accept trickery such as autodiscover.outlook.com.mydomain.com.
            log.debug("Retrieved cname value: %s.", cnameval)
            if str(cnameval) == "autodiscover.outlook.com.":
                return True

        return False

    except dns.exception.DNSException as exc:
        log.debug("Received an expectable error from dns server: %s.", exc)
        return False
