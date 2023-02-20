import json
import subprocess
from typing import Dict, Any, List

from celery import group

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan, init_dict
from websecmap.scanners.models import EndpointGenericScan, Endpoint
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner import allowed_to_scan, constance_json_value
from websecmap.scanners.scanner.filter import merge_endpoints_filter, generic_plan_scan, filter_endpoints_only

"""
DONE: Reduce amount of request, remove redundant scans of other tools (or remove other tools)
DONE: Distribute focus, don't add ssh findings to web scans: connect those to the right endpoint, or add the endpoint.
DONE: How are the templates categorized in nuclei, can we reuse that structure?
DONE: Do not find >low risk findings, as the database might be public. Encrypt everything > low.
DONE: Bundle findings into several categories. Using individual metrics will overflow the end user and nobody will
DONE: Neutralize findings from previous scan that are not mentioned in this scan
DONE: Scan multiple domains at the same time
DONE: Reduce the speed of scans and increase the amount of scans at the same time
TODO: Support custom templates in WSM loaded from database config
TODO: Add uncover integration to get free data from apis: this has a few challenges such as the frequency of updates of
 this data: if that is not updated very frequently we have a problem. My guess is that this data is NOT updated often
 so you will have to buy the products of these companies. Can't blame em. Also at that point you're depending on one
 of these venture backed (most cases) companies that might pivot or go bankrupt in a few years even while their service
 is excellent now.
TODO: Remove even more useless templates and make results more easily understandandable / valuable.
"""


# They use unknown as highest severity, which is plausible since it might be anything.
# Yet that does not mean anything to an end user, so let's set it to the most trivial level and see
# what happens in practice. Perhaps a small adjustment is enough, or unknown should also NOT be scanned.
NUCLEI_SEVERITY_ORDER = [None, "unknown", "info", "low", "medium", "high", "critical"]


# These metrics are already collected in a better way using different scanners. So don't try those again here.
# Todo: this has to come from configuration, that will save some time filtering and allows others to tailor results
REDUNDANT_TEMPLATES = [
    "http-missing-security-headers",
    "deprecated-tls",
    "security-txt",
    "dnssec-detection",
    "dmarc-detect",
    "robots-txt",
    "robots-txt-endpoint",
    "ssl-issuer",
    "xss-deprecated-header",
    "tls-version",
]

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


# todo: move below code into abstraction:
@app.task(queue="kickoff", ignore_result=True)
def plan_scan(**kwargs) -> None:
    # todo: only domains, no subdomains at first.
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, SCANNER_ACTION, filter_endpoints_only, **kwargs)


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs) -> group:
    # 25 matches the bulk size of nuclei
    urls = plannedscan.pickup(activity=SCANNER_ACTION, scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> group:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(organizations_filter, urls_filter, **kwargs)
    # don't scan more than 10, would take far too long otherwise. Scanning by hna dwould not be smart.
    return compose_scan_task(urls[:10])


def compose_scan_task(urls: List[Url]) -> group:
    # make a mapping between endpoint_ids and urls that are being scanned...
    relevant_endpoints = Endpoint.objects.all().filter(url__in=urls, **STANDARD_ENDPOINT_FILTER)

    host_to_endpoint_mapping = {ep.uri_url(): {"endpoint": ep.id, "url": ep.url.id} for ep in relevant_endpoints}
    hosts = list(host_to_endpoint_mapping)

    if not hosts:
        log.debug("No hosts selected for nuclei scan.")
        return group()

    log.debug("Scanning the following hosts: %s", hosts)

    return group(
        scan.s(hosts)
        | store.s(host_to_endpoint_mapping)
        | group(
            plannedscan.finish.si(SCANNER_ACTION, SCANNER_NAME, mapping["url"]) for mapping in host_to_endpoint_mapping
        )
    )


# todo: move above code into abstraction:


@app.task(queue="ipv4")
def scan(urls: List[str]) -> bin:
    # This reduces the standard number of requests from ±1000 to ±700.
    # There will be 2000 templates instead of 4000.

    disabled_templates = constance_json_value("NUCLEI_HTTP_DISABLED_TEMPLATES")

    # probably call a container instead of running this directly?
    # the string[] documentation is vague.
    command = [
        "nuclei",
        # Work with json lines
        "-json",
        # Do not store critical vulnerabilities before they are encrypted
        "-exclude-severity",
        "high",
        "-exclude-severity",
        "critical",
        "-exclude-severity",
        "medium",
        # we don't have to be fast, if we do a LOT of scans at the same time in different tasks
        # Default is 9000 requests per minute (150/s). With 25 hosts in bulk size that would mean 6/second.
        # Let's lower this a bit to be more friendly.
        "-rate-limit",
        "25",
        # Only perform http scans here, don't go digging inside other services and such (perhaps a mutuation of this
        # scanner can do this)
        "-type",
        "http",
        # we are in control of updates:
        "-disable-update-check",
        # no need to see a header
        "-silent",
        # do not scan redundant stuff that we already get elsewhere
        "-exclude-id",
        ",".join(set(REDUNDANT_TEMPLATES + disabled_templates)),
    ]

    for url in urls:
        command += ["-u", url]

    log.debug("Starting nuclei scan with command: %s", command)

    nuc = subprocess.Popen(command, stdout=subprocess.PIPE, env={"HOME": "/opt/nuclei"})
    output = nuc.communicate()

    # Data is returned in jsonl format, binary
    return output[0]


@app.task(queue="storage")
def store(raw_nuclei_data: bin, host_to_endpoint_mapping: Dict[str, Dict[str, int]]) -> None:
    raw_nuclei_records = convert_nuclei_data_to_json(raw_nuclei_data)
    results_per_host = split_nuclei_records_per_host(raw_nuclei_records)

    for host, nuclei_records_per_host in results_per_host.items():
        combined_metrics = prepare_nuclei_results_for_storage(nuclei_records_per_host)

        endpoint_id = host_to_endpoint_mapping[host]["endpoint"]
        for category_name, data in combined_metrics.items():
            store_endpoint_scan_result(category_name, endpoint_id, data["highest-severity"], "", str(data["findings"]))

        # and clean up the stuff that has been solved completely:
        current_categories_of_metrics = list(combined_metrics.keys())
        neutralize_missing_metrics(current_categories_of_metrics, endpoint_id)


def split_nuclei_records_per_host(raw_nuclei_records) -> Dict[str, List[Dict[str, Any]]]:
    # Split results per host, match them to endpoint. Host in the result echos what you throw in to the letter.
    # so: https://example.nl:443 is different from https://example.nl or https://example.nl:443/
    results_per_host = {}
    for record in raw_nuclei_records:
        host = record["host"]
        if host not in results_per_host:
            results_per_host[host] = []
        results_per_host[host].append(record)
    return results_per_host


def prepare_nuclei_results_for_storage(raw_nuclei_records: bin) -> Dict[str, Any]:
    processed_nuclei_records = [process_nuclei_record(record) for record in raw_nuclei_records]
    return combine_processed_nuclei_records(processed_nuclei_records)


def convert_nuclei_data_to_json(data: bin) -> List[Dict[str, Any]]:
    decoded = data.decode("utf-8").replace("\n", ",")
    # remove last comma
    decoded = f"{decoded[:-1]}"
    # add to a list
    listed = f"[{decoded}]"
    return json.loads(listed)


def neutralize_missing_metrics(current_categories_of_metrics: List[str], endpoint_id: int):
    # Add an empty rating to all categories that are in the database, but not in the list.
    non_relevant_scans = (
        EndpointGenericScan.objects.all()
        .filter(endpoint_id=endpoint_id, type__startswith="nuclei_", is_the_latest_scan=True)
        .exclude(type__in=current_categories_of_metrics)
        .exclude(rating="clean")
    )
    for epgs_scan in non_relevant_scans:
        store_endpoint_scan_result(epgs_scan.type, endpoint_id, "clean", "clean", "")


def get_higher_severity(current_severity: str, new_severity: str) -> str:
    current = NUCLEI_SEVERITY_ORDER.index(current_severity)
    new = NUCLEI_SEVERITY_ORDER.index(new_severity)
    return new_severity if new > current else current_severity


def combine_processed_nuclei_records(processed_records) -> Dict[str, Any]:
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
    combined_metrics = {}
    for record in processed_records:
        category = f'nuclei_{record["category"].replace("-", "_")}'
        if category not in combined_metrics:
            combined_metrics[category] = {"highest-severity": "unknown", "amount-of-findings": 0, "findings": []}
        combined_metrics[category]["amount-of-findings"] += 1
        combined_metrics[category]["highest-severity"] = get_higher_severity(
            combined_metrics[category]["highest-severity"], record["severity"]
        )

        # don't mix up severity for end users, they will just not understand it.
        del record["severity"]
        # remove redundant category name
        del record["category"]
        combined_metrics[category]["findings"].append(record)

    return combined_metrics


def process_nuclei_record(n_record: Dict[str, Any]) -> Dict[str, Any]:
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
    template = n_record.get("template", "unknown/")
    category = template[: template.find("/")]

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
        "curl-command": n_record.get("curl-command", ""),
        "extracted-results": n_record.get("extracted-results", []),
        "matched-at": n_record.get("matched-at", ""),
    }

    return {
        "category": category,
        "name": name,
        "severity": severity,
        "finding-name": finding_name,
        "evidence": reduced_evidence,
    }
