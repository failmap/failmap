import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Url, UrlGenericScan

log = logging.getLogger(__package__)


def store_endpoint_scan_result(scan_type: str, endpoint: Endpoint, rating: str, message: str, evidence: str = ""):

    # Check if the latest scan has the same rating or not:
    try:
        gs = EndpointGenericScan.objects.all().filter(
            type=scan_type,
            endpoint=endpoint,
        ).latest('last_scan_moment')
    except ObjectDoesNotExist:
        gs = EndpointGenericScan()

    # last scan had exactly the same result, so don't create a new scan and just update the
    # last scan date.
    if gs.explanation == message and gs.rating == str(rating):
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.save()
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        log.debug("Message or rating changed: making a new generic scan.")
        gs = EndpointGenericScan()
        gs.explanation = message
        gs.rating = rating
        gs.endpoint = endpoint
        gs.type = scan_type
        gs.evidence = evidence
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.rating_determined_on = datetime.now(pytz.utc)
        gs.is_the_latest_scan = True
        gs.save()

        EndpointGenericScan.objects.all().filter(endpoint=gs.endpoint, type=gs.type).exclude(
            pk=gs.pk).update(is_the_latest_scan=False)


def store_url_scan_result(scan_type: str, url: Url, rating: str, message: str, evidence: str = ""):

    # Check if the latest scan has the same rating or not:
    try:
        gs = UrlGenericScan.objects.all().filter(
            type=scan_type,
            url=url,
        ).latest('last_scan_moment')
    except ObjectDoesNotExist:
        gs = UrlGenericScan()

    # here we figured out that you can still pass a bool while type hinting.
    # log.debug("Explanation new: '%s', old: '%s' eq: %s, Rating new: '%s', old: '%s', eq: %s" %
    #           (message, gs.explanation, message == gs.explanation, rating, gs.rating, str(rating) == gs.rating))

    # last scan had exactly the same result, so don't create a new scan and just update the last scan date.
    # while we have type hinting, it's still possible to pass in a boolean and then you compare a str to a bool...
    if gs.explanation == message and gs.rating == str(rating):
        log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.save(update_fields=['last_scan_moment'])
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        log.debug("Message or rating changed: making a new generic scan.")
        gs = UrlGenericScan()
        gs.explanation = message
        gs.rating = rating
        gs.url = url
        gs.evidence = evidence
        gs.type = scan_type
        gs.last_scan_moment = datetime.now(pytz.utc)
        gs.rating_determined_on = datetime.now(pytz.utc)
        gs.is_the_latest_scan = True
        gs.save()

        UrlGenericScan.objects.all().filter(url=gs.url, type=gs.type).exclude(
            pk=gs.pk).update(is_the_latest_scan=False)


def store_historic_endpoint_scan_result(scan_type: str, endpoint: Endpoint, rating: str, message: str, evidence: str,
                                        rating_determined_on, last_scan_moment, is_latest):

    # Check if the latest scan has the same rating or not:
    try:
        gs = EndpointGenericScan.objects.all().filter(
            type=scan_type,
            endpoint=endpoint,
            rating_determined_on__lte=rating_determined_on
        ).latest('last_scan_moment')
    except ObjectDoesNotExist:
        gs = EndpointGenericScan()

    # last scan had exactly the same result, so don't create a new scan and just update the
    # last scan date.
    if gs.explanation == message and gs.rating == rating:
        # log.debug("Scan had the same rating and message, updating last_scan_moment only.")
        gs.last_scan_moment = last_scan_moment
        gs.save()
    else:
        # message and rating changed for this scan_type, so it's worth while to save the scan.
        # log.debug("Message or rating changed: making a new generic scan.")
        gs = EndpointGenericScan()
        gs.explanation = message
        gs.rating = rating
        gs.endpoint = endpoint
        gs.type = scan_type
        gs.evidence = evidence
        gs.last_scan_moment = last_scan_moment
        gs.rating_determined_on = rating_determined_on
        gs.is_the_latest_scan = is_latest
        gs.save()

        # override auto now add..
        gs.last_scan_moment = last_scan_moment
        gs.save()

        EndpointGenericScan.objects.all().filter(endpoint=gs.endpoint, type=gs.type).exclude(
            pk=gs.pk).update(is_the_latest_scan=False)


def endpoint_has_scans(scan_type: str, endpoint: Endpoint):
    """
    Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
    to zero (or another rating)
    :param scan_type:
    :param endpoint:
    :return:
    """

    try:
        gs = EndpointGenericScan.objects.all().filter(
            type=scan_type,
            endpoint=endpoint,
        ).latest('last_scan_moment')
        if gs.rating:
            return True
    except ObjectDoesNotExist:
        return False
