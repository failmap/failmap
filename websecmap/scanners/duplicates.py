from datetime import timedelta

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
    for endpoint in Endpoint.objects.all().order_by("-discovered_on"):
        log.info(f"Attempting to deduplicate: {endpoint}")
        # Always fetch the latest endpoint state, because it might have been changed by an update.
        fresh_endpoint = Endpoint.objects.all().filter(id=endpoint.id).first()
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
    transfer_endpoint_data(fromm=endpoint, to=older_endpoint)
    transfer_endpoint_state(fromm=endpoint, to=older_endpoint)
    # deduplicate_scans(older_endpoint)
    delete_endpoint(endpoint)


def delete_endpoint(endpoint: Endpoint):
    endpoint.delete()


def transfer_endpoint_data(fromm: Endpoint, to: Endpoint):
    updated = EndpointGenericScan.objects.all().filter(endpoint=fromm).update(endpoint=to)
    log.info(updated)
    Screenshot.objects.all().filter(endpoint=fromm).update(endpoint=to)


def transfer_endpoint_state(fromm: Endpoint, to: Endpoint):
    to.is_dead = fromm.is_dead
    to.is_dead_since = fromm.is_dead_since
    to.is_dead_reason = fromm.is_dead_reason
    to.save()


def get_older_duplicate_endpoint(endpoint, within_days: int = 60):
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
