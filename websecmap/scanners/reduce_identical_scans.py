"""
Helps cleanup the database of non-normalized records of scanners that had non-normalized results.
"""
from datetime import datetime, timezone
from typing import Union

from celery import group

from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.models import UrlGenericScan, EndpointGenericScan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata


def get_model_type_from_scan_type(scan_type):
    metadata = get_backend_scanmetadata()
    return "endpoint" if scan_type in metadata["endpoint_scan_types"] else "url"


def reduce_normalized_identical_scans(scan_type) -> group:
    # return a group, so it can be run while testing as apply_sync, while in production apply_async.
    # Make sure the scan results are normalized before running this!

    # see if the previous one is the same after normalization.
    # If that is the case, merge the two scans into one.
    # Retry again and repeat.
    # If the previous result is different, then work backwards from that result and try again and again
    model_type = get_model_type_from_scan_type(scan_type)
    tasks = []

    if model_type == "endpoint":
        ids_that_have_this_scan = (
            EndpointGenericScan.objects.all().filter(type=scan_type).values_list("endpoint__id", flat=True)
        )
        tasks.extend(
            reduce_normalized_scan_per_endpoint.si(id, "endpoint", scan_type) for id in ids_that_have_this_scan
        )
    if model_type == "url":
        ids_that_have_this_scan = UrlGenericScan.objects.all().filter(type=scan_type).values_list("url__id", flat=True)
        tasks.extend(reduce_normalized_scan_per_endpoint.si(id, "url", scan_type) for id in ids_that_have_this_scan)

    return group(tasks)


@app.task(queue="storage")
def reduce_normalized_scan_per_endpoint(endpoint_or_ur_id: int, url_or_endpoint: str, scan_type: str):
    # this code is possibly a duplicate of deduplicate_all_scans_sequentially... only per endpoint so faster.
    now = datetime.now(timezone.utc)
    current_scan = get_scan(now, scan_type, url_or_endpoint, endpoint_or_ur_id)

    if not current_scan:
        log.debug("There is no scan on this %s: %s", url_or_endpoint, endpoint_or_ur_id)
        return

    # this can be performed for each different endpoint / url simultaneously.
    while current_scan:
        previous_scan = get_scan(
            current_scan.rating_determined_on, scan_type, url_or_endpoint, endpoint_or_ur_id, current_scan.id
        )

        if not previous_scan:
            log.debug("No older scans found, so we're done.")
            return

        if scan_is_identical(current_scan, previous_scan):
            merge_scans(current_scan, previous_scan)
        else:
            # let's try to see what happens with the previous scan, until
            log.debug("Scan differed, so setting the current scan to the previous scan and taking it from there.")
            current_scan = previous_scan


def get_scan(when, scan_type, url_or_endpoint, endpoint_or_ur_id, exclude_for_previous: int = 0):
    # ugly abstractions are ugly
    model = EndpointGenericScan if url_or_endpoint == "endpoint" else UrlGenericScan

    current_scan = model.objects.all().filter(type=scan_type, rating_determined_on__lte=when)

    if url_or_endpoint == "endpoint":
        current_scan = current_scan.filter(endpoint=endpoint_or_ur_id)
    else:
        current_scan = current_scan.filter(url=endpoint_or_ur_id)

    if exclude_for_previous:
        current_scan = current_scan.exclude(id=exclude_for_previous)

    current_scan = current_scan.order_by("-rating_determined_on")

    return current_scan.first()


def scan_is_identical(
    newer_scan: Union[EndpointGenericScan, UrlGenericScan], older_scan: Union[EndpointGenericScan, UrlGenericScan]
) -> bool:
    # See scanmanager.py when something is new / identical
    if newer_scan.rating != older_scan.rating:
        return False
    if newer_scan.evidence != older_scan.evidence:
        return False
    if newer_scan.explanation != older_scan.explanation:
        return False
    # omitting empty string values and {}
    if newer_scan.meaning and older_scan.meaning and newer_scan.meaning != older_scan.meaning:
        return False

    return True


def merge_scans(
    newer_scan: Union[EndpointGenericScan, UrlGenericScan], older_scan: Union[EndpointGenericScan, UrlGenericScan]
):
    log.debug("Merging scans: %s and %s", newer_scan, older_scan)
    newer_scan.rating_determined_on = older_scan.rating_determined_on

    # if there was an explanation on either, keep at least one:
    if older_scan.comply_or_explain_is_explained and not newer_scan.comply_or_explain_is_explained:
        newer_scan.comply_or_explain_is_explained = True
        newer_scan.comply_or_explain_explanation = older_scan.comply_or_explain_explanation
        newer_scan.comply_or_explain_explained_on = older_scan.comply_or_explain_explained_on
        newer_scan.comply_or_explain_explained_by = older_scan.comply_or_explain_explained_by
        newer_scan.comply_or_explain_explanation_valid_until = older_scan.comply_or_explain_explanation_valid_until
        newer_scan.comply_or_explain_case_additional_notes = older_scan.comply_or_explain_case_additional_notes
        newer_scan.comply_or_explain_case_handled_by = older_scan.comply_or_explain_case_handled_by

    newer_scan.save()
    log.debug("Deleting older scan: %s", older_scan)
    older_scan.delete()
