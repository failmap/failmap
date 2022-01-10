from datetime import timedelta

from celery import group

from websecmap.celery import app, EXPIRES_IN_ONE_DAY
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner import unique_and_random, finish_those_that_wont_be_scanned
from websecmap.scanners.scanner.autoexplain_trust_microsoft import (
    autoexplain_trust_microsoft_and_include_their_webserver_headers,
)

SCANNER = "autoexplain_no_https_possible"

query = EndpointGenericScan.objects.all().filter(
    type="plain_https",
    is_the_latest_scan=True,
    rating="1000",
)

# The PKI domain is excepted as it often hosted Certificate Revocation Lists
# The CRL domain is excepted for the same reason. Running https there could cause all kinds of confusion
# Note that "is public information so should be unencrypted" is a weak argument: integrity and confidentiality are
#  mandatory properties for public information.
excepted_subdomains = ["pki", "crl"]


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_scan():
    scans = query.filter(
        endpoint__url__computed_subdomain__in=excepted_subdomains, comply_or_explain_is_explained=False
    )
    urls = [endpoint_generic_scan.endpoint.url for endpoint_generic_scan in scans]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    scans = query.filter(endpoint__url__in=urls).only("id", "endpoint__url__id")
    finish_those_that_wont_be_scanned(SCANNER, scans, urls)

    return group(
        [
            scan.si(scan_id=endpoint_generic_scan.pk)
            | plannedscan.finish.si("scan", SCANNER, endpoint_generic_scan.endpoint.url.pk)
            for endpoint_generic_scan in list(set(scans))
        ]
    )


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def scan(scan_id: int):

    a_scan = EndpointGenericScan.objects.all().filter(id=scan_id).first()
    if not a_scan:
        return

    # Only 1000: where there is NO https. 25 points is a redirect, which is not OK for PKI/CRL!
    if not a_scan.rating == "1000":
        return

    if a_scan.endpoint.url.computed_subdomain not in excepted_subdomains:
        return

    # The plain_https rating is removed
    add_bot_explanation(a_scan, "domain_hosts_certificate_revocation_list", timedelta(days=365 * 10))

    # Also remove associated HSTS header rating, there will not be a HSTS of course for this domain.
    autoexplain_trust_microsoft_and_include_their_webserver_headers(a_scan)
