import json
import logging
from multiprocessing.pool import ThreadPool

from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner.plain_http import clean_can_connect_result_evidence
from websecmap.scanners.scanner.security_headers import reduce_url

log = logging.getLogger(__name__)


def get_scans(scan_type: str):
    return EndpointGenericScan.objects.all().filter(type=scan_type).values_list("id", flat=True)


def clean_plain_http_no_https_redirect_no_https_on_standard_port_evidence():
    scans = (
        EndpointGenericScan.objects.all()
        .filter(rating="no_https_redirect_and_no_https_on_standard_port")
        .values_list("id", flat=True)
    )
    parallelize(something_something_plain_http_no_https_redirect_no_https_on_standard_port_evidence, scans, 25)


def something_something_plain_http_no_https_redirect_no_https_on_standard_port_evidence(scan_id):
    epgs = EndpointGenericScan.objects.filter(id=scan_id).only("evidence").first()
    if not epgs:
        log.debug("No scan with id: %s", scan_id)
        return

    if epgs.evidence:
        epgs.evidence = clean_can_connect_result_evidence(epgs.evidence)
        epgs.save(update_fields=["evidence"])


def clean_http_security_header_strict_transport_security():
    # removes all the headers except for location and strict-transport-security for every request
    # reduces the url to only the url and path. Afterwards remove duplicates using the existing methods.
    scans = get_scans("http_security_header_strict_transport_security")
    log.debug("Cleaning %s hsts scans.", len(scans))
    parallelize(something_something_hsts, scans, 25)
    log.debug("Done cleaning up")


def something_something_hsts(scan_id):
    log.debug("Scan id: %s", scan_id)
    epgs = EndpointGenericScan.objects.filter(id=scan_id).only("evidence").first()
    log.debug("Scan id3: %s", scan_id)
    if not epgs:
        log.debug("No scan with id: %s", scan_id)
        return

    log.debug("Scan id2: %s", scan_id)

    if epgs.evidence:
        log.debug("Scan id4: %s", scan_id)
        epgs.evidence = reduce_hsts_evidence(epgs.evidence)
        epgs.save(update_fields=["evidence"])
    else:
        log.debug("Scan id5: %s", scan_id)


def try_get_json(data):
    try:
        return json.loads(data)
    except json.decoder.JSONDecodeError:
        return None


def reduce_hsts_evidence(evidence: str) -> str:
    # example_hsts_evidence = [
    #     {
    #         "request": 1,
    #         "url": "https://mijn.preprod1.digid.nl:443/",
    #         "protocol": "https",
    #         "status_code": 302,
    #         "content_type": "text/html; charset=utf-8",
    #         "headers": {
    #             "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self
    #             "content-type": "text/html; charset=utf-8",
    #             "location": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3a%2f%2fmijn.pre
    #             "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),
    #             "referrer-policy": "same-origin",
    #             "strict-transport-security": "max-age=31536000 ; includesubdomains",
    #             "x-content-type-options": "nosniff",
    #             "x-frame-options": "sameorigin",
    #             "x-xss-protection": "1; mode=block",
    #         },
    #     },
    #     {
    #         "request": 2,
    #         "url": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3A%2F%2Fmijn.preprod1.dig
    #         "protocol": "https",
    #         "status_code": 302,
    #         "content_type": "text/html; charset=utf-8",
    #         "headers": {
    #             "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self
    #             "content-type": "text/html; charset=utf-8",
    #             "location": "https://preprod1.digid.nl/cookies_geblokkeerd?process=my_digid&url=https%3a%2f%2fmijn.pr
    #             "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),
    #             "referrer-policy": "same-origin",
    #             "strict-transport-security": "max-age=31536000 ; includesubdomains",
    #             "x-content-type-options": "nosniff",
    #             "x-frame-options": "sameorigin",
    #             "x-xss-protection": "1; mode=block",
    #         },
    #     },
    # ]

    requests = try_get_json(evidence)
    if not requests:
        log.debug("No requests 1")
        return evidence

    if len(requests) == 0:
        log.debug("No requests 2")
        return evidence

    if "status_code" not in requests[0]:
        # probably another format
        log.debug("Incorrect format")
        return evidence

    for request in requests:
        request["url"] = reduce_url(request["url"])
        new_headers = {}
        if "strict-transport-security" in request["headers"]:
            new_headers["strict-transport-security"] = request["headers"].pop("strict-transport-security")

        if "location" in request["headers"]:
            new_headers["location"] = reduce_url(request["headers"].pop("location"))

        request["headers"] = new_headers

    return json.dumps(requests)


def parallelize(method, parameters, poolsize: int = 25):
    pool = ThreadPool(poolsize)

    for parameter in parameters:
        pool.apply_async(method, [parameter])

    pool.close()
    pool.join()

    log.debug("Done with parallelization")
