import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Url, UrlGenericScan

log = logging.getLogger(__package__)


def store_endpoint_scan_result(scan_type: str, endpoint_id: int, rating: str, message: str, evidence: str = ""):

    # Check if the latest scan has the same rating or not:
    try:
        gs = EndpointGenericScan.objects.all().filter(type=scan_type, endpoint=endpoint_id).latest("last_scan_moment")
        exists = True
    except ObjectDoesNotExist:
        exists = False
        gs = EndpointGenericScan()

    # To deduplicate data, only store changes to scans. We'll update just the scan moment, and the rest stays the same.
    # The amount of data saved runs in the gigabytes. So it's worth the while doing it like this :)
    if gs.explanation == str(message) and gs.rating == str(rating):
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.save(update_fields=["last_scan_moment"])
        return

    # message and rating changed for this scan_type, so it's worth while to save the scan.
    if not exists:
        log.debug("No prior scan result found, creating a new one.")
    else:
        log.debug("Message or rating changed compared to previous scan. Saving the new scan result.")

    gs = EndpointGenericScan()
    # very long csp headers for example
    gs.explanation = message[0:255]
    gs.rating = rating
    gs.endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    gs.type = scan_type
    # Very long CSP headers for example take a lot of space.
    gs.evidence = evidence[0:9000]
    gs.last_scan_moment = datetime.now(pytz.utc)
    gs.rating_determined_on = datetime.now(pytz.utc)
    gs.is_the_latest_scan = True
    gs.save()

    # Set all the previous endpoint scans of this endpoint + type to NOT be the latest scan.
    EndpointGenericScan.objects.all().filter(endpoint=gs.endpoint, type=gs.type).exclude(pk=gs.pk).update(
        is_the_latest_scan=False
    )


def store_url_scan_result(scan_type: str, url_id: int, rating: str, message: str, evidence: str = ""):

    # Check if the latest scan has the same rating or not:
    try:
        gs = (
            UrlGenericScan.objects.all()
            .filter(
                type=scan_type,
                url=url_id,
            )
            .latest("last_scan_moment")
        )
    except ObjectDoesNotExist:
        gs = UrlGenericScan()

    # here we figured out that you can still pass a bool while type hinting.
    # log.debug("Explanation new: '%s', old: '%s' eq: %s, Rating new: '%s', old: '%s', eq: %s" %
    #           (message, gs.explanation, message == gs.explanation, rating, gs.rating, str(rating) == gs.rating))

    # last scan had exactly the same result, so don't create a new scan and just update the last scan date.
    # while we have type hinting, it's still possible to pass in a boolean and then you compare a str to a bool...
    if gs.explanation == str(message) and gs.rating == str(rating):
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.save(update_fields=["last_scan_moment"])
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        log.debug("Message or rating changed: making a new generic scan.")
        gs = UrlGenericScan()
        gs.explanation = message
        gs.rating = rating
        gs.url = Url.objects.all().filter(id=url_id).first()
        gs.evidence = evidence
        gs.type = scan_type
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.rating_determined_on = datetime.now(pytz.utc)
        gs.is_the_latest_scan = True
        gs.save()

        UrlGenericScan.objects.all().filter(url=gs.url, type=gs.type).exclude(pk=gs.pk).update(is_the_latest_scan=False)


def endpoint_has_scans(scan_type: str, endpoint_id: int):
    """
    Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
    to zero (or another rating)
    :param scan_type:
    :param endpoint_id:
    :return:
    """

    try:
        gs = (
            EndpointGenericScan.objects.all()
            .filter(
                type=scan_type,
                endpoint=endpoint_id,
            )
            .latest("last_scan_moment")
        )
        if gs.rating:
            return True
    except ObjectDoesNotExist:
        return False
