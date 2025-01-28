"""
Check if a domain is only reachable on plain http, instead of both http and https.

Browsers first connect to http, not https when entering a domain. That will be changed in the future.

Further reading:
https://stackoverflow.com/questions/20475552/python-requests-library-redirect-new-url#20475712
"""

import json
import logging
import re
from typing import Dict, List, Union

from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanmanager import endpoint_has_scans, store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to
from websecmap.scanners.scanner.filter import (
    apply_organzation_or_endpoint_filter_before_url_filter,
    merge_organizations_filter,
    merge_urls_filter,
)
from websecmap.scanners.scanner.http import (
    can_connect,
    connect_result,
    redirects_to_safety,
    resolves_on_v4,
    resolves_on_v6,
)
from websecmap.scanners.scanner.utils import IP_QUEUES

log = logging.getLogger(__package__)

# These messages are translated and expected lateron. Don't edit them unless you're also editing them in the reporting
# etc etc.
CLEANED_UP = "Has a secure equivalent, which wasn't so in the past."
NOT_RESOLVABLE_AT_ALL = "Cannot be resolved anymore, seems to be cleaned up."
SAVED_BY_THE_BELL = "Redirects to a secure site, while a secure counterpart on the standard port is missing."
NO_HTTPS_AT_ALL = "Site does not redirect to secure url, and has no secure alternative on a standard port."


SCANNER_NAME = "plain_http"
STANDARD_ORGANIZATION_FILTER = {"is_dead": False}
STANDARD_URL_FILTER = {"is_dead": False, "not_resolvable": False, "endpoint__protocol": "http", "endpoint__port": 80}


@app.task(queue="kickoff", ignore_result=True)
def scan_all(**kwargs):
    if not allowed_to("scan", SCANNER_NAME):
        return group()

    kwargs = merge_urls_filter(STANDARD_URL_FILTER, **kwargs)
    urls = apply_organzation_or_endpoint_filter_before_url_filter(**kwargs)
    tasks = compose_scan_tasks(urls)
    for task in tasks:
        task.apply_async(**kwargs.get("task_arguments", {}))

    return group()


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> group:
    if not allowed_to("scan", SCANNER_NAME):
        return group()

    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    kwargs = merge_urls_filter(STANDARD_URL_FILTER, urls_filter=urls_filter)
    # only if the organization is filtered... otherwise the organization filter is always triggered by the default.
    if kwargs.get("organizations_filter", {}):
        kwargs = merge_organizations_filter(STANDARD_ORGANIZATION_FILTER, **kwargs)
    urls = apply_organzation_or_endpoint_filter_before_url_filter(**kwargs)
    return group(compose_scan_tasks(urls))


def compose_scan_tasks(urls: List[Url]) -> List[Task]:
    tasks = []
    for url in urls:
        complete_endpoints, incomplete_endpoints = get_endpoints_with_missing_encryption(url)

        tasks.extend(well_done.si(complete_endpoint.pk) for complete_endpoint in complete_endpoints)

        tasks.extend(
            scan.si(incomplete_endpoint.ip_version, incomplete_endpoint.url.url).set(
                queue=IP_QUEUES[incomplete_endpoint.ip_version]
            )
            | store.s(incomplete_endpoint.pk)
            for incomplete_endpoint in incomplete_endpoints
        )
    return tasks


def get_endpoints_with_missing_encryption(url):
    """
    Finds a list of endpoints that are missing an encrypted counterpart. Takes in account ip_version.

    The default ports matter for normal humans. All services on other ports are special services.
    we only give points if there is not a normal https site when there is a normal http site.
    :param url:
    :return:
    """

    endpoints = (
        Endpoint.objects.all()
        .filter(url=url, is_dead=False)
        .only("id", "protocol", "port", "ip_version", "url__id", "url__url")
    )

    has_http_v4, has_https_v4, has_http_v6, has_https_v6 = False, False, False, False
    http_v4_endpoint, http_v6_endpoint = None, None
    complete_endpoints, incomplete_endpoints = [], []

    for endpoint in endpoints:
        if endpoint.protocol == "http" and endpoint.port == 80 and endpoint.ip_version == 4:
            has_http_v4 = True
            http_v4_endpoint = endpoint
        if endpoint.protocol == "https" and endpoint.port == 443 and endpoint.ip_version == 4:
            has_https_v4 = True

        if endpoint.protocol == "http" and endpoint.port == 80 and endpoint.ip_version == 6:
            has_http_v6 = True
            http_v6_endpoint = endpoint

        if endpoint.protocol == "https" and endpoint.port == 443 and endpoint.ip_version == 6:
            has_https_v6 = True

    if has_http_v4:
        if has_https_v4:
            complete_endpoints.append(http_v4_endpoint)
        else:
            incomplete_endpoints.append(http_v4_endpoint)
    if has_http_v6:
        if has_https_v6:
            complete_endpoints.append(http_v6_endpoint)
        else:
            incomplete_endpoints.append(http_v6_endpoint)
    return complete_endpoints, incomplete_endpoints


@app.task(queue="storage", ignore_result=True)
def well_done(endpoint_id):
    if endpoint_has_scans("plain_http", endpoint_id):
        store_endpoint_scan_result("plain_http", endpoint_id, "redirecting_properly", CLEANED_UP)


# Task is written to work both on v4 and v6, but the network conf of the machine differs.
@app.task()
def scan(ip_version: int, url: str, user_agent: str):
    """
    Using an incomplete endpoint

    # calculate the score
    # Organizations with wildcards can have this problem a lot:
    # 1: It's not possible to distinguish the default page with another page, wildcards
    #    can help hide domains and services.
    # 2: A wildcard TLS connection is an option: then it will be fine, and it can be also
    #    run only on everything that is NOT another service on the server: also hiding stuff
    # 3: Due to SNI it's not possible where something is served.

    # !!! The only solution is to have a "curated" list of port 80 websites. !!!
    # maybe compare an image of a non existing url with the random ones given here.
    # if they are the same, then there is really no site. That should help clean
    # non-existing wildcard domains.

    # Comparing with screenshots is simply not effective enough:
    # 1: Many HTTPS sites load HTTP resources, which don't show, and thus it's different.
    # 2: There is no guarantee that a wildcard serves a blank page.
    # 3: In the transition phase to default https (coming years), it's not possible to say
    #    what should be the "leading" site.

    :param endpoint:
    :return:
    """

    # if the address doesn't resolve, why bother scanning at all?
    resolves = False
    if ip_version == 4:
        resolves = resolves_on_v4(url)
    elif ip_version == 6:
        resolves = resolves_on_v6(url)

    if not resolves:
        # no need to further check, can't even get the IP address...
        return False, False, False

    # if you cannot connect to a secure endpoint, we're going to find out of there is redirect.
    # The worker (should) only resolve domain names only over ipv4 or ipv6. (A / AAAA).
    # Currenlty docker does not support that. Which means a lot of network rewriting for dealing with
    # all edge cases of HTTP.

    # retry harder!
    can_connect_result = can_connect(
        protocol="https", hostname=url, port=443, ip_version=ip_version, user_agent=user_agent
    )

    if isinstance(can_connect_result, Exception):
        log.error("can_connect timed out: %s", can_connect_result)
        return False, False, False

    redirects_to_safety_result = None if can_connect_result["result"] else redirects_to_safety(f"http://{url}:80")

    return resolves, can_connect_result, redirects_to_safety_result


def clean_can_connect_result_evidence(result_text):
    # Will remove the memory address and timeout number because those change over time.
    # HTTPSConnectionPool(host='example.nl', port=443): Max retries exceeded with url: / (Caused by
    # ConnectTimeoutError(<urllib3.connection.HTTPSConnection object at 0x7f2368f44310>,
    # 'Connection to example.nl timed out. (connect timeout=15)'))
    result_text = replace_memory_address_in_string(result_text)

    return result_text


def replace_memory_address_in_string(text):
    # regex that replaces 0xhex-string to 0xmemory_address
    text = re.sub(r"0x[a-f0-9]{12,24}", r"0xmemory_address", text)
    return text


@app.task(queue="storage", ignore_result=True)
def store(results, endpoint_id):
    resolves, can_connect_result, redirects_to_safety_result = results
    if redirects_to_safety_result:
        redirects_to_safety_boolean, redirects = redirects_to_safety_result
    else:
        redirects_to_safety_boolean = False
        redirects = []

    resolves: bool = resolves
    can_connect_result: Dict[str, Union[str, bool]] = can_connect_result

    if not resolves:
        # Don't administrate endpoints that don't resolve, that is a task for the http verify scanner. Here we just
        # don't try to redirect to safety or otherwise miscalculate the result. If the http verify scanner is not run
        # there will be mismatches between this (or previous results) and reality.
        log.debug(
            "Endpoint on %s doesn't resolve anymore. "
            "Run the DNS verify scanner to prevent scanning non resolving endpoints.",
            endpoint_id,
        )
        return

    endpoint = Endpoint.objects.all().filter(id=endpoint_id).only("ip_version", "url__id").first()
    if not endpoint:
        return

    connect_result(
        result=can_connect_result,
        protocol="https",
        url_id=endpoint.url.pk,
        port=443,
        ip_version=endpoint.ip_version,
        origin="plain_http",
    )

    # issue resolved: there was a scan in the past and now there is an https connection possible.
    # So store it, but also add evidence, so we can inspect pingpong issues.
    # We're not interested if we can't connect or if we didn't have an issue in the past...
    if can_connect_result["result"] and endpoint_has_scans("plain_http", endpoint_id):
        store_endpoint_scan_result(
            # todo: this is not 'redirecting_properly': because there is no redirect. It should be named
            #  connecting properly. And this is weird, as there is a ping pong between nothing there and
            #  connecting properly.
            scan_type="plain_http",
            endpoint_id=endpoint_id,
            rating="redirecting_properly",
            message=CLEANED_UP,
            evidence=json.dumps(can_connect_result),
        )
        return

    # Really no security at all
    if not can_connect_result["result"]:
        if redirects_to_safety_boolean:
            # some redirections that might have flaws etc.
            log.info("%s redirects to safety, saved by the bell.", endpoint.url)
            store_endpoint_scan_result(
                "plain_http",
                endpoint_id,
                "https_redirect_on_insecure_port_and_no_https_on_standard_port",
                SAVED_BY_THE_BELL,
                evidence=json.dumps({"redirects": redirects}),
            )
            return

        # no redirects...
        if "error" in can_connect_result:
            can_connect_result["error"] = clean_can_connect_result_evidence(can_connect_result["error"])

        log.info("%s does not have a https site. Saving/updating scan.", endpoint.url)
        store_endpoint_scan_result(
            "plain_http",
            endpoint_id,
            "no_https_redirect_and_no_https_on_standard_port",
            NO_HTTPS_AT_ALL,
            evidence=json.dumps(can_connect_result),
        )
