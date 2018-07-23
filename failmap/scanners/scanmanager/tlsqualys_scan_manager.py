import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist

from failmap.scanners.models import Endpoint, TlsQualysScan

log = logging.getLogger(__package__)


class TlsQualysScanManager:
    """
    Helps with data deduplication of scans. Helps storing scans in a more generic way.

    :return:
    """
    @staticmethod
    def add_scan(endpoint: Endpoint, rating: str, rating_no_trust: str, message: str):

        # Check if the latest scan has the same rating or not:
        try:
            gs = TlsQualysScan.objects.all().filter(
                endpoint=endpoint,
            ).latest('last_scan_moment')
        except ObjectDoesNotExist:
            gs = TlsQualysScan()

        # last scan had exactly the same result, so don't create a new scan and just update the
        # last scan date.
        if gs.qualys_message == message and gs.qualys_rating == rating and gs.qualys_rating_no_trust == rating_no_trust:
            log.debug("Scan had the same rating and message, updating last_scan_moment only.")
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.save()
        else:
            # message and rating changed for this scan_type, so it's worth while to save the scan.
            log.debug("Message or rating changed: making a new generic scan.")
            gs = TlsQualysScan()
            gs.endpoint = endpoint
            gs.qualys_rating = rating
            gs.qualys_rating_no_trust = rating_no_trust
            gs.qualys_message = message
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.rating_determined_on = datetime.now(pytz.utc)
            gs.scan_time = datetime.now(pytz.utc)
            gs.scan_date = datetime.now(pytz.utc)
            gs.save()

    @staticmethod
    def had_scan_with_points(endpoint: Endpoint):
        """
        Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
        to zero (or another rating)
        :param scan_type:
        :param endpoint:
        :return:
        """

        try:
            gs = TlsQualysScan.objects.all().filter(
                endpoint=endpoint,
            ).latest('last_scan_moment')
            if gs.rating:
                return True
        except ObjectDoesNotExist:
            return False
