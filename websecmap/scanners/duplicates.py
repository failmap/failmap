from datetime import timedelta
from typing import Optional

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Screenshot
import logging

log = logging.getLogger(__package__)


def deduplicate_all_endpoints_sequentially(days: int = 60):
    """
    This iterates over all endpoints from new to old and removes the newest stuff if the older endpoint exists.
    This assumes that you can have gaps between endpoint detection of N days, those gaps will be closed.

    It will move stuff to the older endpoint and delete the newest endpoint.

    It's not the fastest algorithm, but it's easy to understand and maintain. That helps a lot :)

    Days: the amount of days between the current endpoint and the last endpoint. This is the maximum gap that will
    be merged.
    """

    # Iterate over all endpoints from new to old. So all endpoints exist. id descending, newest first.
    for endpoint_id in Endpoint.objects.all().order_by("-discovered_on").only("id").values_list("id", flat=True):
        log.info(f"Attempting to deduplicate: {endpoint_id}")
        # Always fetch the latest endpoint state, because it might have been changed by an update.
        fresh_endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
        if not fresh_endpoint:
            continue
        reduce_if_duplicate_endpoint(fresh_endpoint, days)
    log.info("done")


def reduce_if_duplicate_endpoint(endpoint: Endpoint, days: int = 60):
    # Do just one pass: if there is an older endpoint, remove the current one and switch to the older one.
    # Copy the state of the current one to the older one so it's probably alive.
    older_endpoint = get_older_duplicate_endpoint(endpoint, within_days=days)
    if not older_endpoint:
        log.info(f"No older endpoint exists for {endpoint} in the last {days} days.")
        return

    log.info(f"Going to transfer data from {endpoint} to {older_endpoint}.")
    # Move all the older stuff to the older endpoint, but set the older endpoint to the current state.
    # This will make the endpoint alive, probably, as that is most likely to be the current state.
    # Afterwards this endpoint becomes useless and can be deleted.
    # When transitioning all scans of this endpoint, there might be duplicates, where the older might
    # have explanations already.
    transfer_endpoint_data(fromm=endpoint, to_ep=older_endpoint)
    transfer_endpoint_state(fromm=endpoint, to_ep=older_endpoint)
    # deduplicate_scans(older_endpoint)
    delete_endpoint(endpoint)


def delete_endpoint(endpoint: Endpoint):
    endpoint.delete()


def transfer_endpoint_data(fromm: Endpoint, to_ep: Endpoint):
    updated = EndpointGenericScan.objects.all().filter(endpoint=fromm).update(endpoint=to_ep)
    log.info(updated)
    Screenshot.objects.all().filter(endpoint=fromm).update(endpoint=to_ep)


def transfer_endpoint_state(fromm: Endpoint, to_ep: Endpoint):
    to_ep.is_dead = fromm.is_dead
    to_ep.is_dead_since = fromm.is_dead_since
    to_ep.is_dead_reason = fromm.is_dead_reason
    to_ep.save()


def get_older_duplicate_endpoint(endpoint: Endpoint, within_days: int = 60):
    # Determine if there is an older duplicate endpoint. If that exists, then return it.

    # No discovery date, doesn't make sense, can't deal with that.
    if endpoint.discovered_on is None:
        return None

    return (
        Endpoint.objects.all()
        .filter(
            url=endpoint.url,
            protocol=endpoint.protocol,
            port=endpoint.port,
            ip_version=endpoint.ip_version,
            # can only be newer than N days
            discovered_on__gte=endpoint.discovered_on - timedelta(days=within_days),
            # has to be older, can't be newer than yourself.
            discovered_on__lte=endpoint.discovered_on,
        )
        .exclude(pk=endpoint.pk)
        # id descending, so the newest one first.
        .order_by("-discovered_on")
        .first()
    )


def deduplicate_all_scans_sequentially():
    """
    Go over each scan, if there is an older scan with the same attributes, merge the newer one into the older,
    basically by changing the 'latest scan' and date information. In both cases: if there is an explanation
    keep it. If both have an explanation just use the old one.

    Many explanations get lost because of a new endpoint and thus a new scan. This causes a storm of e-mails
    when there is a DNS outage or something like that.

    The newest stuff is always being deleted, that's why this works without too much hassle.
    UrlGenericScan is not used now, as there have NEVER been explains about DNSSEC. There might be in the future.
    """

    for epgs_id in (
        EndpointGenericScan.objects.all().order_by("-rating_determined_on").only("id").values_list("id", flat=True)
    ):
        log.info("Attempting to deduplicate: {%s}", epgs_id)
        # Always fetch the latest endpoint state, because it might have been changed by an update.
        fresh_epgs = EndpointGenericScan.objects.all().filter(id=epgs_id).first()
        if not fresh_epgs:
            continue
        reduce_if_duplicate_scan(fresh_epgs)
    log.info("done")


def reduce_if_duplicate_scan(scan: EndpointGenericScan):
    older_scan = get_older_duplicate_scan(scan)
    if not older_scan:
        log.info("No older endpoint exists for {%s}.", scan)
        return

    log.info("Going to transfer data from {%s} to {%s}.", scan, older_scan)
    # when both scans where stored at the same time, one is the latest scan. Merge those too.
    if not older_scan.is_the_latest_scan:
        log.info("Transferred latest scan information")
        older_scan.is_the_latest_scan = scan.is_the_latest_scan
        if scan.is_the_latest_scan:
            log.info("Newest scan is the latest scan and has been transferred.")
    else:
        log.info("Older scan already is the latest scan, not changing it.")

    # Only if there was no explanation, migrate the comply or explain data from the newer scan.
    if not older_scan.comply_or_explain_is_explained:
        log.info("Transferred comply or explain information")
        older_scan.comply_or_explain_is_explained = scan.comply_or_explain_is_explained
        older_scan.comply_or_explain_case_additional_notes = scan.comply_or_explain_case_additional_notes
        older_scan.comply_or_explain_case_handled_by = scan.comply_or_explain_case_handled_by
        older_scan.comply_or_explain_explained_by = scan.comply_or_explain_explained_by
        older_scan.comply_or_explain_explained_on = scan.comply_or_explain_explained_on
        older_scan.comply_or_explain_explanation = scan.comply_or_explain_explanation
        older_scan.comply_or_explain_explanation_valid_until = scan.comply_or_explain_explanation_valid_until
    else:
        log.info("Older scan was already explained, not copying newer data.")

    # Migrate the last scan moment
    log.debug(
        "Migrating the last scan moment, setting it to the newer scan. "
        "From {%s} to {%s}", older_scan.last_scan_moment, scan.last_scan_moment
    )
    older_scan.last_scan_moment = scan.last_scan_moment
    older_scan.save()

    log.info("Scan migrated to older scan, removing the newer scan as it has no additional value.")
    scan.delete()


def get_older_duplicate_scan(scan: EndpointGenericScan) -> Optional[EndpointGenericScan]:
    # This has to ONLY check for the most recent scan before this one, and THEN see if that one is the same.
    # It should not dig in the entire past.
    possible_duplicate = (
        EndpointGenericScan.objects.all()
        .filter(endpoint=scan.endpoint, type=scan.type, last_scan_moment__lte=scan.last_scan_moment)
        .exclude(pk=scan.pk)
        .order_by("-last_scan_moment")
        .first()
    )

    if not possible_duplicate:
        log.info("No previous scan found for this endpoint.")
        return None

    # The metrics have to be exactly the same, the rest of the state such as explanation and latest scan field
    # can deviate.
    if not all(
        [
            possible_duplicate.rating == scan.rating,
            possible_duplicate.explanation == scan.explanation,
            possible_duplicate.evidence == scan.evidence,
        ]
    ):
        log.info("Previous scan had different characteristics, cannot deduplicate.")
        return None

    log.info("Found a previous scan for {%s}, which is {%s}.", scan, possible_duplicate)
    return possible_duplicate
