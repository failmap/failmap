import logging
import os
import copy
import json
import subprocess
from typing import Any, Iterable, TypedDict
import typing

from celery import Signature, group

from websecmap.celery import app
from websecmap.map.logic.login_plaza import generated_login_portal_meaning_data
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, EndpointGenericScan, Scanner, ScannerFinding, Product
from websecmap.scanners.scanmanager import Meaning, store_endpoint_scan_result
from websecmap.scanners.scanner import (
    allowed_to_scan,
    constance_json_value,
    unique_and_random,
)
from websecmap.scanners.scanner.filter import (
    ObjectFilter,
    filter_endpoints_only,
    generic_plan_scan,
    merge_endpoints_filter,
)
from websecmap.scanners.scanner.security_headers import remove_random_identifiers
from websecmap.scanners.scanner.utils import dict_chunks
from websecmap.scanners.support import kwargs_to_params

"""
DONE: Reduce amount of request, remove redundant scans of other tools (or remove other tools)
DONE: Distribute focus, don't add ssh findings to web scans: connect those to the right endpoint, or add the endpoint.
DONE: How are the templates categorized in nuclei, can we reuse that structure?
DONE: Do not find >low risk findings, as the database might be public. Encrypt everything > low.
DONE: Bundle findings into several categories. Using individual metrics will overflow the end user and nobody will
DONE: Neutralize findings from previous scan that are not mentioned in this scan
DONE: Scan multiple domains at the same time
DONE: Reduce the speed of scans and increase the amount of scans at the same time
DONE: Add optimized verification
TODO: Support custom templates in WSM loaded from database config
TODO: Add uncover integration to get free data from apis: this has a few challenges such as the frequency of updates of
 this data: if that is not updated very frequently we have a problem. My guess is that this data is NOT updated often
 so you will have to buy the products of these companies. Can't blame em. Also at that point you're depending on one
 of these venture backed (most cases) companies that might pivot or go bankrupt in a few years even while their service
 is excellent now.
DONE: Remove even more useless templates and make results more easily understandandable / valuable.
DONE: Add sub-scanners based on this scanner with just a set of templates, to lower the amount of requests.
"""

log = logging.getLogger(__name__)

NUCLEI_BIN = os.environ.get("NUCLEI_BIN", "/usr/local/bin/nuclei")

# They use unknown as highest severity, which is plausible since it might be anything.
# Yet that does not mean anything to an end user, so let's set it to the most trivial level and see
# what happens in practice. Perhaps a small adjustment is enough, or unknown should also NOT be scanned.
NUCLEI_SEVERITY_ORDER = [None, "unknown", "info", "low", "medium", "high", "critical"]


SCANNER_NAME = "nuclei_http"
SCANNER_ACTION = "scan"

# narrow down to the most restrictive set of domains, as the scanner is/can be pretty heavy on resource
# Site should be the same on v4 and v6 anyway... so don't bother with differences
# todo: support more ports, ip-versions (is a param in nuclei) and perhaps protocols...
STANDARD_ENDPOINT_FILTER = {
    "protocol": "https",
    "is_dead": False,
    "url__is_dead": False,
    "url__not_resolvable": False,
    "ip_version": 4,
    "port": 443,
}

# this saves about 3000 scans mostly on microsoft environments.
EXCLUDED_SUBDOMAINS = [
    "autodiscover",
    "sip",
    "lyncdiscover",
    "adfs",
    "enterpriseenrollment",
    "enterpriseregistration",
]

DEFAULT_CHUNK_SIZE = 25

NUCLEI_ARGUMENTS = {
    "panels_and_tech": {
        "args": [
            {"name": "silent", "type": "no-value"},
            {"name": "disable-update-check", "type": "no-value"},
            # TODO: this should be configurable more dynamically
            {"name": "rate-limit", "type": "single-argument", "value": "10"},
            {"name": "config-directory", "type": "single-argument", "value": "/tmp"},
            {"name": "type", "type": "list-to-duplicate-arguments", "value": ["http"]},
            {
                "name": "include-templates",
                "type": "list-to-duplicate-arguments",
                "value": ["exposed-panels", "technologies"],
            },
            {
                "name": "exclude-templates",
                "type": "list-to-duplicate-arguments",
                "value": [
                    "cnvd",
                    "cves",
                    "default-logins",
                    "dns",
                    "exposures",
                    "file",
                    "fuzzing",
                    "headless",
                    "iot",
                    "miscellaneous",
                    "misconfiguration",
                    "network",
                    "ssl",
                    "takeovers",
                    "token-spray",
                    "vulnerabilities",
                    "workflows",
                ],
            },
            # TODO: user agent should come from central config
            {
                "name": "header",
                "type": "single-argument",
                "value": (
                    "'User-Agent: Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P)"
                    " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.62 Mobile Safari/537.36"
                    " (compatible; ICF-Basisbeveiliging/1.0; +https://internetcleanup.foundation/scaninfo)'"
                ),
            },
            {
                "name": "exclude-severity",
                "type": "list-to-duplicate-arguments",
                "value": ["high", "critical", "medium"],
            },
            {"name": "exclude-id", "type": "list-to-single-csv-argument", "value": ["robots-txt", "security-txt"]},
        ],
        # this should be configurable
        "amount": DEFAULT_CHUNK_SIZE,
    }
}
DEFAULT_NUCLEI_ARGUMENTS = "panels_and_tech"


# todo: move below code into abstraction:
@app.task(queue="kickoff", ignore_result=True)
def plan_scan_plannedscan(**kwargs) -> None:
    # uses plannedscan table for queueing
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, SCANNER_ACTION, filter_endpoints_only, **kwargs)


@app.task(queue="kickoff", ignore_result=True)
def plan_verify() -> None:
    scans = (
        EndpointGenericScan.objects.all()
        .filter(
            type__in=[
                "nuclei_exposed_panels",
                "nuclei_exposures",
                "nuclei_http",
                "nuclei_miscellaneous",
                "nuclei_misconfiguration",
                "nuclei_technologies",
                "nuclei_unknown",
                "nuclei_vulnerabilities",
            ],
            is_the_latest_scan=True,
            endpoint__url__not_resolvable=False,
            endpoint__url__is_dead=False,
            endpoint__is_dead=False,
        )
        # you cannot verify clean endpoints because it is not clear what templates need to be used for
        # rescan. If there is something new there, it will pop up in the next large sweep scan.
        .exclude(rating="clean")
        .select_related("endpoint", "endpoint__url")
        .only(
            "endpoint__url",
            "rating_determined_on",
            "type",
            "rating",
            "endpoint__is_dead",
            "endpoint__ip_version",
            "endpoint__port",
            "endpoint__protocol",
        )
        # disable default ordering because it is expensive and doesn't matter in this case
        .order_by()
    )

    urls = unique_and_random([scan.endpoint.url for scan in scans])
    plannedscan.request(activity="verify", scanner=SCANNER_NAME, urls=urls)


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs) -> group:
    # 25 matches the bulk size of nuclei
    urls = plannedscan.pickup(activity=SCANNER_ACTION, scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls, kwargs)


@app.task(queue="kickoff", ignore_result=True)
def scan_all(amount: int = DEFAULT_CHUNK_SIZE):
    """This function is executed at a regular interval by the scheduler to perform scans
    on all endpoints for all organizations for all layers for all countries."""

    if not allowed_to_scan(SCANNER_NAME):
        return

    # get all endpoints without filters applied
    urls = filter_endpoints_only({}, {}, {})

    # TODO: allow passing scanner arguments from schedule
    for task in compose_scan_task(urls, scanner_keyword_arguments={}, amount=amount):
        log.debug("Enqueueing task: %s", task)
        task.apply_async()


def compose_manual_scan_task(
    organizations_filter: ObjectFilter, urls_filter: ObjectFilter, endpoints_filter: ObjectFilter, force: bool = False
) -> Iterable[Signature[None]]:
    if not allowed_to_scan(SCANNER_NAME) and not force:
        return []

    urls = filter_endpoints_only(organizations_filter, urls_filter, endpoints_filter)
    return group(compose_scan_task(urls, scanner_keyword_arguments={}))


def compose_scan_task(
    urls: Iterable[Url], scanner_keyword_arguments: dict[str, Any], amount: int = DEFAULT_CHUNK_SIZE
) -> Iterable[Signature[None]]:
    endpoints = Endpoint.objects.all().filter(url__in=urls, **STANDARD_ENDPOINT_FILTER)
    # log.debug("Got %s endpoints after standard filter: %s", len(endpoints), STANDARD_ENDPOINT_FILTER)

    endpoints = endpoints.exclude(url__computed_subdomain__in=EXCLUDED_SUBDOMAINS).only(
        "id", "ip_version", "protocol", "port", "url__url"
    )
    # log.debug("Got %s endpoints after excluding domains: %s", len(endpoints), EXCLUDED_SUBDOMAINS)

    # make a mapping between endpoint_ids and urls that are being scanned...
    host_to_endpoint_mapping: dict[str, dict[str, int]] = {
        ep.uri_url(): {"endpoint": ep.id, "url": ep.url.id} for ep in endpoints if ep.url
    }

    # log.debug("Got %s unique hosts", len(host_to_endpoint_mapping))

    if not host_to_endpoint_mapping:
        log.debug("No hosts selected for nuclei scan.")
        return

    if not scanner_keyword_arguments:
        scanner_keyword_arguments = NUCLEI_ARGUMENTS[DEFAULT_NUCLEI_ARGUMENTS]
        log.debug("No nuclei arguments specified, using default '%s'", DEFAULT_NUCLEI_ARGUMENTS)
    log.debug("Nuclei arguments: %s", scanner_keyword_arguments)

    disabled_templates: list[str] = constance_json_value("NUCLEI_HTTP_DISABLED_TEMPLATES")
    # Split list of hosts into chunks, so one scan tasks can run multiple scans in parallel using it's own threading
    # logic. This saves time and resources
    for chunk in dict_chunks(host_to_endpoint_mapping, amount):
        yield (
            scan_batch.s(
                urls=list(chunk),
                scanner_keyword_arguments=scanner_keyword_arguments,
                disabled_templates=disabled_templates,
            )
            | store_scan_batch.s(host_to_endpoint_mapping=chunk)
        )


@app.task(queue="kickoff")
def compose_planned_verify_task(**kwargs) -> group:
    # 25 matches the bulk size of nuclei
    urls = plannedscan.pickup(activity="verify", scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_verify_task(urls, kwargs)


def compose_manual_verify_task(
    organizations_filter: ObjectFilter, urls_filter: ObjectFilter, endpoints_filter: ObjectFilter, **kwargs
) -> group:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_endpoints_only(organizations_filter, urls_filter, endpoints_filter)
    return compose_verify_task(urls)


def compose_verify_task(urls: list[Url], scanner_keyword_arguments: dict[str, Any] = None) -> group:
    # re-scan an endpoint only using the templates used in the results. This saves a few hundred requests every time.
    # The templates are named explicitly in the results.
    current_scans = (
        EndpointGenericScan.objects.all()
        .filter(
            type__in=[
                "nuclei_exposed_panels",
                "nuclei_exposures",
                "nuclei_http",
                "nuclei_miscellaneous",
                "nuclei_misconfiguration",
                "nuclei_technologies",
                "nuclei_unknown",
                "nuclei_vulnerabilities",
            ],
            is_the_latest_scan=True,
            endpoint__url__not_resolvable=False,
            endpoint__url__is_dead=False,
            endpoint__is_dead=False,
            endpoint__url__url__in=urls,
        )
        .select_related("endpoint", "endpoint__url")
        .only(
            "evidence",
            "type",
            "endpoint__url__url",
            "endpoint__id",
            "endpoint__url__id",
            "endpoint__port",
            "endpoint__protocol",
            "endpoint__ip_version",
        )
    )
    if not len(current_scans):
        # why is there a difference between what has been planned to verify and the query here?
        # anyway: no scans means that we can finish these tasks...
        # perhaps the url died?
        return group([plannedscan.finish.si("verify", SCANNER_NAME, url.id) for url in urls])

    # there might be some scans, but not for all urls, which means those urls will be left over and never finished
    # so figure out what urls have scans and finish the rest after this.
    all_urls: list[int] = [url.id for url in urls]  # finish goes via the name of the url not the id.
    urls_rescanned: list[int] = []

    tasks = []
    for current_scan in current_scans:
        url_id = current_scan.endpoint.url.id
        urls_rescanned.append(url_id)

        # when something is clean up, it will be empty. So there is a scan but no data...
        template_ids = get_templates_from_scan_results(evidence_to_json(current_scan.evidence))
        if not template_ids:
            tasks.append(plannedscan.finish.si("verify", SCANNER_NAME, url_id))
            continue

        scan_these_templates = {"name": "template-id", "type": "list-to-duplicate-arguments", "value": template_ids}
        # merge scanner params with the templates that need to be used for the rescan
        if scanner_keyword_arguments and "args" in scanner_keyword_arguments:
            args_copy = copy.deepcopy(scanner_keyword_arguments)
            args_copy["args"].append(scan_these_templates)
            params = args_copy
        else:
            params = {"args": [scan_these_templates]}

        tasks.append(
            scan_batch.s([current_scan.endpoint.uri_url()], params)
            | store_verify_results.s(current_scan.endpoint.id, current_scan.type)
            | plannedscan.finish.si("verify", SCANNER_NAME, url_id)
        )

    # figure out non-rescanned urls, finish them as well:
    missing = list(set(all_urls) - set(urls_rescanned))
    tasks.extend(plannedscan.finish.si("verify", SCANNER_NAME, url_id) for url_id in missing)

    return group(tasks)


def evidence_to_json(processed_nuclei_data) -> Any:
    try:
        return json.loads(processed_nuclei_data)
    except json.decoder.JSONDecodeError as e:
        log.debug("Nuclei data not parseable, %s", e)
        log.debug("Nuclei data: %s", processed_nuclei_data)
        return []


def get_templates_from_scan_results(json_data, field="template-id") -> list[str]:
    if len(json_data) == 0:
        log.debug("No nuclei records found")
        return []

    disabled_templates = constance_json_value("NUCLEI_HTTP_DISABLED_TEMPLATES")

    templates = []
    for result in json_data:
        possible_result = result.get(field, "unknown")
        if possible_result not in disabled_templates + ["unknown"]:
            templates.append(possible_result)

    # do not return duplicate templates, one 'waf-detect' is enough
    # order it to get consistent scans and testable commands
    return list(sorted(list(set(templates))))


def create_nuclei_scan_command(
    urls: list[str],
    nuclei_bin: str = NUCLEI_BIN,
    scanner_keyword_arguments: dict[str, Any] | None = None,
    disabled_templates: list[str] | None = None,
):
    # probably call a container instead of running this directly?
    # the string[] documentation is vague.
    command = [
        nuclei_bin,
        "-jsonl",
    ]

    if scanner_keyword_arguments:
        command += kwargs_to_params(scanner_keyword_arguments, prefix="-")

    if disabled_templates:
        if disabled_string := ",".join(disabled_templates):
            command += [
                # do not scan redundant stuff that we already get elsewhere
                "-exclude-id",
                disabled_string,
            ]

    for url in urls:
        command += ["-u", url]

    return command


@app.task(queue="nucleiv4")
def scan_batch(
    urls: list[str], scanner_keyword_arguments: dict[str, Any], disabled_templates: list[str] | None = None
) -> bytes:
    # This reduces the standard number of requests from ±1000 to ±700.
    # There will be 2000 templates instead of 4000.

    command = create_nuclei_scan_command(
        urls, scanner_keyword_arguments=scanner_keyword_arguments, disabled_templates=disabled_templates
    )
    log.debug("Starting nuclei scan with command: %s", " ".join(command))

    nuc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/tmp")
    stdout, stderr = nuc.communicate()
    for line in stderr:
        log.error("nuclei stderr: %r", line)

    exit_code = nuc.returncode
    if exit_code != 0:
        log.error("Nuclei finished with non-zero exit code: %s", exit_code)

    log.debug(
        "Finished nuclei scan with command: %s, exit code: %s, output: %s...", " ".join(command), exit_code, stdout[:32]
    )

    # Data is returned in jsonl format, binary
    return stdout


class StorageResult(TypedDict, total=False):
    success: bool
    endpointgenericscan_ids: list[int]
    # TODO: python3.10 make NotRequired
    endpoints_killed: int
    endpoints_saved: int


@app.task(queue="storage")
def store_scan_batch(raw_nuclei_data: bytes, host_to_endpoint_mapping: dict[str, dict[str, int]]) -> StorageResult:
    """
    In a new nuclei scan, you do not know what categories are scanned and what metrics are actually returned:
    nuclei only returns data if a scan was successful. So you might get less categories than you requested etc.
    In a new scan just dump whatever you find to the database: the scan types are derived from the scan data.
    """

    raw_nuclei_records = convert_nuclei_data_to_json(raw_nuclei_data)
    results_per_host = split_nuclei_records_per_host(raw_nuclei_records)
    log.debug("Nuclei results per host: %s", json.dumps(results_per_host, indent=2))

    # todo: what if raw_nuclei_records is empty? what host exactly should then be cleaned?
    # at verify the nr of hosts/endpoints is always 1. So that should then be cleaned if there
    # are no records?

    saved_endpoint_ids: list[int] = list()

    for host, nuclei_records_per_host in results_per_host.items():
        combined_metrics = prepare_nuclei_results_for_storage(nuclei_records_per_host)

        try:
            endpoint_id = host_to_endpoint_mapping[host]["endpoint"]
            for category_name, data in combined_metrics.items():
                rating = rate_nuclei_finding(category_name, data)
                # todo: we want to handle the 'tech' metrics first, as that creates meaning for the portal scans in
                #  the report.
                # todo: add meaning, so make sure tech is done first. Doesn't matter as it is cached.

                meaning: Meaning = {}
                if category_name == "nuclei_exposed_panels":
                    meaning = {"tech": generated_login_portal_meaning_data(data["findings"], endpoint_id)}

                saved_endpoint = store_endpoint_scan_result(
                    category_name,
                    endpoint_id,
                    rating,
                    "",
                    # Has to be readable by the verify scanner
                    # prevents a ping-pong issue with evidence, where phpMyAdmin and phpmyadmin cycle new evidence.
                    evidence=json.dumps(data["findings"]).lower(),
                    meaning=meaning,
                )
                saved_endpoint_ids.append(saved_endpoint.id)

        except KeyError as e:
            # ssl/ssl-dns-names.yaml will alter the 'host' from https://pw.tweedekamer.nl:443 to pw.tweedekamer.nl
            # and without host you don't know to what endpoint to save specifically? Perhaps a mapping can be made
            # so there are fallback hosts / urls etc.
            # monitor exceptions for a while
            log.exception(
                "Could not find host from nuclei report in host-endpoint-mapping",
                extra={
                    "host": host,
                    "ndpoint_id": host_to_endpoint_mapping,
                    "combined_metrics": combined_metrics,
                    "exception": e,
                },
            )

    return {"success": True, "endpointgenericscan_ids": saved_endpoint_ids}


def rate_nuclei_finding(nuclei_finding_name: str, data: dict[str, str | None]) -> str:
    if nuclei_finding_name == "nuclei_exposed_panels":
        return rate_nuclei_portal_finding(data["findings"])

    return data["highest-severity"]


# just so we can call it from a webinterface
@app.task(queue="storage", ignore_result=True)
def rerate_portal_findings():
    scans = EndpointGenericScan.objects.all().filter(type="nuclei_exposed_panels", is_the_latest_scan=True)

    for scan in scans:
        ev = evidence_to_json(scan.evidence)
        rating = rate_nuclei_portal_finding(ev)
        scan.rating = rating

        # also add the meaning if we can?
        scan.meaning = {"tech": generated_login_portal_meaning_data(ev, scan.endpoint.id)}

        scan.save()


def rate_nuclei_portal_finding(findings_data: list[dict[str, Any]]) -> str:
    # scan templates are already converted to products. get that product and see the portal value for severity.
    # this also has to include some meaning. Or will we do that in the description?
    # developer / internal management tooling
    # internal management tooling

    templates = get_templates_from_scan_results(findings_data, "finding-name")

    # Done: might be valuable to have the products stuff cached to prevent a ton of queries for the same
    # products... It's just a few thousands queries. So whatever...
    # get all portal names, then see if that portal has an associated product and a risk
    impacts = []
    products = Product.objects.all().filter(scanner_finding_name_mapping__name__in=templates)
    for product in products:
        if product.login_panel_presence_security_impact:
            impacts.append(product.login_panel_presence_security_impact.name)

    # and here we go, already need the prioritization of the impacts...
    prios = ["ok", "low", "medium", "high"]
    highest_impact = 0
    for impact in impacts:
        if prios.index(impact) > highest_impact:
            highest_impact = prios.index(impact)

    return prios[highest_impact]


@app.task(queue="storage", ignore_result=True)
def store_verify_results(raw_nuclei_data: bytes, endpoint_id: int, scan_type: str) -> None:
    """
    A verify scan knows what scan has been performed. Nuclei does not return data in case it has not found anything,
    in that case we just neutralize a missing if it exists for that category.

    This assumes that a scan type contains all possible scans.
    """
    raw_nuclei_records = convert_nuclei_data_to_json(raw_nuclei_data)
    if not raw_nuclei_records:
        neutralize_specific_metric([scan_type], endpoint_id=endpoint_id)
        return

    # Story anything you get back under the known category. It could be that scans have been moved to
    # different categories and such. The result is always whatever you asked to scan or a subset.
    # todo: add meaning, so make sure tech is done first, doesn't matter, it works with cached data anyway.
    #  this means that it can take a rescan till all the stuff is correct and some new record is written. Which is ok.
    #  for now.
    data = force_combine_all_processed_metrics_into_one_category(raw_nuclei_records)
    rating = rate_nuclei_finding(scan_type, data)
    store_endpoint_scan_result(
        scan_type,
        endpoint_id,
        rating,
        "",
        evidence=json.dumps(data["findings"]).lower(),
        # put it in some key, so other stuff can be appended to it lateron if need be
        meaning={"tech": generated_login_portal_meaning_data(data["findings"], endpoint_id)},
    )


def split_nuclei_records_per_host(raw_nuclei_records) -> dict[str, list[dict[str, str]]]:
    # Split results per host, match them to endpoint. Host in the result echos what you throw in to the letter.
    # so: https://example.nl:443 is different from https://example.nl or https://example.nl:443/
    results_per_host = {}
    for record in raw_nuclei_records:
        host = record["host"]
        if host not in results_per_host:
            results_per_host[host] = []
        results_per_host[host].append(record)
    return results_per_host


def prepare_nuclei_results_for_storage(raw_nuclei_records: list[dict[str, str]]) -> dict[str, dict[str, str | None]]:
    processed_nuclei_records = [process_nuclei_record(record) for record in raw_nuclei_records]
    return combine_processed_nuclei_records(processed_nuclei_records)


def convert_nuclei_data_to_json(data: bytes | str) -> list[dict[str, str | None]]:
    try:
        decoded = data.decode("utf-8") if isinstance(data, bytes) else data
        decoded = decoded.strip()
        decoded = decoded.replace("\n", ",")
        # remove last comma
        decoded = decoded.rstrip(",")
        # add to a list
        listed = f"[{decoded}]"
        result = typing.cast(list[dict[str, str | None]], json.loads(listed))
    except Exception:
        log.debug("Raw nuclei data: %s", data)
        log.exception("Error during converting nuclei data to JSON")
        raise

    return result


def neutralize_missing_metrics(current_categories_of_metrics: list[str], endpoint_id: int):
    # Add an empty rating to all categories that are in the database, but not in the list.
    non_relevant_scans = (
        EndpointGenericScan.objects.all()
        .filter(
            endpoint_id=endpoint_id,
            type__in=[
                "nuclei_exposed_panels",
                "nuclei_exposures",
                "nuclei_http",
                "nuclei_miscellaneous",
                "nuclei_misconfiguration",
                "nuclei_technologies",
                "nuclei_unknown",
                "nuclei_vulnerabilities",
            ],
            is_the_latest_scan=True,
        )
        .exclude(type__in=current_categories_of_metrics)
        .exclude(rating="clean")
    )
    for epgs_scan in non_relevant_scans:
        store_endpoint_scan_result(epgs_scan.type, endpoint_id, "clean", "clean", "")


def neutralize_specific_metric(current_categories_of_metrics: list[str], endpoint_id: int):
    # it's not clear why one would want to use the neutralize_missing_metrics routine:
    # - A verification is for a specific scan type. And thus exluding that same scan type from cleanup
    #   will prevent the neutralization for that specific type will never happen(!)
    non_relevant_scans = (
        EndpointGenericScan.objects.all()
        .filter(
            endpoint_id=endpoint_id,
            type__in=current_categories_of_metrics,
            is_the_latest_scan=True,
        )
        .exclude(rating="clean")
    )
    for epgs_scan in non_relevant_scans:
        store_endpoint_scan_result(epgs_scan.type, endpoint_id, "clean", "clean", "")


def get_higher_severity(current_severity: str, new_severity: str) -> str:
    current = NUCLEI_SEVERITY_ORDER.index(current_severity)
    new = NUCLEI_SEVERITY_ORDER.index(new_severity)
    return new_severity if new > current else current_severity


def combine_processed_nuclei_records(processed_records) -> dict[str, dict[str, str | None]]:
    """
    Combined metrics based on category. Adding all into one. This results into just a few categories for
    nuclei, instead of a ridiculously large number of findings that will have all to be displayed, translated,
    and so on. Each of these categories will be saved to their own database result.

    This will result into a list like this:

    "nuclei-misconfiguration": {
        "highest-severity": "high",
        "amount-of-findings": 10,
        "findings": [... list of relevant processed records ...]
    }
    """
    combined_metrics: dict[str, Any] = {}
    for record in processed_records:
        category = f'nuclei_{record["category"].replace("-", "_")}'
        if category not in combined_metrics:
            combined_metrics[category] = {"highest-severity": "unknown", "amount-of-findings": 0, "findings": []}
        combined_metrics[category]["amount-of-findings"] += 1
        combined_metrics[category]["highest-severity"] = get_higher_severity(
            combined_metrics[category]["highest-severity"], record["severity"]
        )

        record = clean_nuclei_record(record)
        combined_metrics[category]["findings"].append(record)

    # sort the findings on template-id, name and finding-name, otherwise they will be stored again and again
    # in different orders
    for category in combined_metrics:
        combined_metrics[category]["findings"] = sorted(
            combined_metrics[category]["findings"],
            key=lambda k: (k.get("template-id", None), k.get("name", None), k.get("finding-name", None)),
        )

    return combined_metrics


def force_combine_all_processed_metrics_into_one_category(raw_nuclei_records):
    processed_nuclei_records = [process_nuclei_record(record) for record in raw_nuclei_records]

    combined_metrics = {"highest-severity": "unknown", "amount-of-findings": 0, "findings": []}
    # in this case category is not relevant:
    for record in processed_nuclei_records:
        combined_metrics["highest-severity"] = get_higher_severity(
            combined_metrics["highest-severity"], record["severity"]
        )
        combined_metrics["amount-of-findings"] += 1
        record = clean_nuclei_record(record)
        combined_metrics["findings"].append(record)

    # sort the findings on template-id, name and finding-name, otherwise they will be stored again and again
    # in different orders
    combined_metrics["findings"] = sorted(
        combined_metrics["findings"],
        key=lambda k: (k.get("template-id", None), k.get("name", None), k.get("finding-name", None)),
    )
    return combined_metrics


def clean_nuclei_record(record):
    # don't mix up severity for end users, they will just not understand it.
    del record["severity"]
    # remove redundant category name
    del record["category"]
    return record


def categories_from_template(template: str) -> str:
    """Get (sub)categories from template name path.

    >>> categories_from_template("http/exposed-panels/phpmyadmin-panel.yaml")
    'exposed-panels'

    >>> categories_from_template('technologies/tech-detect.yaml')
    'technologies'

    >>> categories_from_template('unknown/')
    'unknown'
    """

    # because exposed-panels and technologies used to be subcatogories of their own but since last year not anymore
    # remove the http/ prefix from template paths so we don't have to refactor everything right now in regards of
    # template names to endpointgenericscan type (eg nuclei_exposed_panels, nuclei_technologies)
    backward_compatible_template = template.removeprefix("http/")
    category = backward_compatible_template[: backward_compatible_template.find("/")]

    return category


def process_nuclei_record(n_record: dict[str, Any]) -> dict[str, Any]:
    # Just the raw nuclei data, not combined at all. These might not be really helpful.
    # template_id is ambiguous. The matcher name makes it unique.

    template_id = n_record.get("template-id", "unknown")

    if "matcher-name" in n_record:
        finding_name = f"nuclei-{template_id}-{n_record.get('matcher-name', 'unknown')}".replace("-", "_")
    else:
        finding_name = f"nuclei-{template_id}".replace("-", "_")

    severity = n_record.get("info", {}).get("severity", "unknown")
    name = n_record.get("info", {}).get("name", "unknown")

    # to categorize findings, use the directory of the template.
    # Which support things like exposed-panels, iot, token-sprak, takeover, fuzzing, exposures, default-logins,
    # technologies, network, misconfiguration, miscellaneous. We can merge the findings per category so there
    # are just ±20 new metrics instead of many thousands.
    # nuclei templates have 2 layers of directories in which templates are contained, we are interested in the
    # second directory
    template = n_record.get("template", "unknown/")
    category = categories_from_template(template)

    # Reduce the amount of metadata to save on storage. This _DOES_ remove some credits where credits are due, so
    # that has to be solved somehow. If we DO add it now, the people reading these findings will try to contact
    # these people, and that should be the last thing on their mind.

    """
    "matched-at": "https://www.example.com/phpmyadmin/",
    "extracted-results": [
        "4.9.0.1"
    ],
    """
    reduced_evidence = {
        # This is so much data, and nobody needs this... so please...
        # "curl-command": n_record.get("curl-command", ""),
        "extracted-results": n_record.get("extracted-results", []),
        # Remove GUIDS and other random identifiers from the url, otherwise a new
        # evidence record is created every visit (which is a waste of space)
        "matched-at": remove_random_identifiers(n_record.get("matched-at", "")),
    }

    return {
        "category": category,
        # for verify scans, this saves re-running everything again...
        "template-id": n_record.get("template-id", "unknown"),
        "name": name,
        "severity": severity,
        "finding-name": finding_name,
        "evidence": reduced_evidence,
    }


@app.task(queue="storage", ignore_result=True)
def extract_findings_to_scanner_findings():
    # Gets the finding-name and nice name and puts it in the ScannerFinding table.
    # This is useful to create mappings between scanner findings and products.
    # Many findings all point to the same product.
    # Example data:
    # [{"template-id": "waf-detect", "name": "WAF Detection", "finding-name": "nuclei_waf_detect_apachegeneric",
    # "evidence": {"extracted-results": [], "matched-at": ""}}]
    # And other example data:
    # [{"template-id": "rstudio-detect", "name": "RStudio Panel - Detect", "finding-name": "nuclei_rstudio_detect",
    # "evidence": {"extracted-results": [], "matched-at": ""}}]

    scanner = Scanner.objects.all().filter(name="nuclei_http").first()
    if not scanner:
        log.warning("No nuclei_http scanner found, cannot extract findings.")
        return

    # do not attempt to re-insert something we already have
    # this reduces many many queries into ±2k
    found_findings_names = []
    for epgs in EndpointGenericScan.objects.all().filter(
        type__in=[
            "nuclei_exposed_panels",
            "nuclei_exposures",
            "nuclei_http",
            "nuclei_miscellaneous",
            "nuclei_misconfiguration",
            "nuclei_technologies",
            "nuclei_unknown",
            "nuclei_vulnerabilities",
        ]
    ):
        json_data = load_finding_data(epgs.evidence)
        for row in json_data:
            if row["finding-name"] in found_findings_names:
                continue
            found_findings_names.append(row["finding-name"])
            ScannerFinding.objects.get_or_create(name=row["finding-name"], nice_name=row["name"], scanner=scanner)


def load_finding_data(data):
    try:
        json_data = json.loads(data)
    except json.decoder.JSONDecodeError:
        json_data = []
    return json_data


def get_all_panels(panel_name: str = "phpmyadmin"):
    # creates a list of all phpmyadmin installations. This is convenient for retesting separately by hand.
    # Used via the shell, not in code here in the app (yet).
    panels = set()
    for epgs in EndpointGenericScan.objects.all().filter(type="nuclei_exposed_panels").order_by("-id"):
        json_data = load_finding_data(epgs.evidence)
        for row in json_data:
            if panel_name.lower() in row["name"].lower():
                panels.add(row["evidence"]["matched-at"])
    return panels
