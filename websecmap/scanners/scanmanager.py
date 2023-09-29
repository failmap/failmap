import logging
from datetime import datetime, timezone
from typing import Union

from django.core.exceptions import ObjectDoesNotExist

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Url, UrlGenericScan

log = logging.getLogger(__package__)


def store_endpoint_scan_result(
    scan_type: str, endpoint_id: int, rating: str, message: str, evidence: str = "", meaning: str = ""
):
    log.debug(
        "Storage requested for scan type %s, endpoint_id %s, rating: %s, message: %s, meaning: %s",
        scan_type,
        endpoint_id,
        rating,
        message,
        meaning,
    )

    # Check if the latest scan has the same rating or not:
    try:
        epgs = EndpointGenericScan.objects.all().filter(type=scan_type, endpoint=endpoint_id).latest("last_scan_moment")
        exists = True
    except ObjectDoesNotExist:
        exists = False
        epgs = EndpointGenericScan()

    # To deduplicate data, only store changes to scans. We'll update just the scan moment, and the rest stays the same.
    # The amount of data saved runs in the gigabytes. So it's worth the while doing it like this :)
    # in privacy metrics the rating may stay the same but the evidence can change. Make sure that this change
    # in evidence is reflected.
    if epgs.explanation == message and epgs.rating == rating and epgs.evidence == evidence and epgs.meaning == meaning:
        log.debug("Scan had the same rating, message and evidence, updating last_scan_moment only.")
        epgs.last_scan_moment = datetime.now(timezone.utc)
        epgs.save(update_fields=["last_scan_moment"])
        return

    # message and rating changed for this scan_type, so it's worth while to save the scan.
    if not exists:
        log.debug("No prior scan result found, creating a new one.")
    else:
        log.debug("Message or rating changed compared to previous scan. Saving the new scan result.")

    epgs = EndpointGenericScan()
    # very long csp headers for example
    epgs.explanation = message[:255]
    epgs.rating = rating
    epgs.endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    epgs.type = scan_type
    # Very long CSP headers for example take a lot of space.
    epgs.evidence = evidence
    epgs.meaning = meaning
    epgs.last_scan_moment = datetime.now(timezone.utc)
    epgs.rating_determined_on = datetime.now(timezone.utc)
    epgs.is_the_latest_scan = True
    epgs.save()

    # Set all the previous endpoint scans of this endpoint + type to NOT be the latest scan.
    EndpointGenericScan.objects.all().filter(
        endpoint=epgs.endpoint,
        type=epgs.type,
        # speed up by only finding the ones that are true, not all results ofc!
        is_the_latest_scan=True,
    ).exclude(pk=epgs.pk).update(is_the_latest_scan=False)

    return epgs


def store_url_scan_result(scan_type: str, url_id: int, rating: str, message: str, evidence: str = ""):
    # Check if the latest scan has the same rating or not:
    try:
        ugs = (
            UrlGenericScan.objects.all()
            .filter(
                type=scan_type,
                url=url_id,
            )
            .latest("last_scan_moment")
        )
    except ObjectDoesNotExist:
        ugs = UrlGenericScan()

    # here we figured out that you can still pass a bool while type hinting.
    # log.debug("Explanation new: '%s', old: '%s' eq: %s, Rating new: '%s', old: '%s', eq: %s" %
    #           (message, gs.explanation, message == gs.explanation, rating, gs.rating, str(rating) == gs.rating))

    # last scan had exactly the same result, so don't create a new scan and just update the last scan date.
    # while we have type hinting, it's still possible to pass in a boolean and then you compare a str to a bool...
    if ugs.explanation == message and ugs.rating == rating and ugs.evidence == evidence:
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        ugs.last_scan_moment = datetime.now(timezone.utc)
        ugs.save(update_fields=["last_scan_moment"])
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        log.debug("Message or rating changed: making a new generic scan.")
        ugs = UrlGenericScan()
        ugs.explanation = message
        ugs.rating = rating
        ugs.url = Url.objects.all().filter(id=url_id).first()
        ugs.evidence = evidence
        ugs.type = scan_type
        ugs.last_scan_moment = datetime.now(timezone.utc)
        ugs.rating_determined_on = datetime.now(timezone.utc)
        ugs.is_the_latest_scan = True
        ugs.save()

        UrlGenericScan.objects.all().filter(
            url=ugs.url,
            type=ugs.type,
            # speed up by only finding the ones that are true, not all results ofc!
            is_the_latest_scan=True,
        ).exclude(pk=ugs.pk).update(is_the_latest_scan=False)

        return ugs


def endpoint_has_scans(scan_type: str, endpoint_id: int):
    """
    Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
    to zero (or another rating)
    :param scan_type:
    :param endpoint_id:
    :return:
    """

    try:
        genericscan = (
            EndpointGenericScan.objects.all()
            .filter(
                type=scan_type,
                endpoint=endpoint_id,
            )
            .latest("last_scan_moment")
        )
        if genericscan.rating:
            return True
    except ObjectDoesNotExist:
        return False


def delete_metric_and_set_previous_to_latest(item: Union[EndpointGenericScan, UrlGenericScan]):
    # This helps setting the latest scan of the same scan type to "is the latest" when the latest scan is deleted.

    # no need to transfer the latest scan to another scan.
    if not item.is_the_latest_scan:
        item.delete()

    if item.__class__.__name__ == "EndpointGenericScan":
        manager = EndpointGenericScan
    else:
        manager = UrlGenericScan

    if (
        previous_item := manager.objects.filter(
            endpoint=item.endpoint,
            type=item.type,
        )
        .exclude(id=item.id)
        .order_by("-id")
        .first()
    ):
        previous_item.is_the_latest_scan = True
        previous_item.save()

    item.delete()
