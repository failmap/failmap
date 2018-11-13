import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist

from failmap.scanners.models import Endpoint, EndpointGenericScan

log = logging.getLogger(__package__)


class EndpointScanManager:
    """
    Helps with data deduplication of scans. Helps storing scans in a more generic way.

    :return:
    """
    @staticmethod
    def add_scan(scan_type: str, endpoint: Endpoint, rating: str, message: str, evidence: str = ""):

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
        if gs.explanation == message and gs.rating == rating:
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

    @staticmethod
    def add_historic_scan(scan_type: str, endpoint: Endpoint, rating: str, message: str, evidence: str,
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

    @staticmethod
    def had_scan_with_points(scan_type: str, endpoint: Endpoint):
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
