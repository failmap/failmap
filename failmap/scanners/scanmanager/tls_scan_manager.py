import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist

from failmap.scanners.models import Endpoint, TlsScan

logger = logging.getLogger(__package__)


class TlsScanManager:
    """
    Helps with data deduplication of scans. Helps storing scans in a more generic way.

    :return:
    """
    @staticmethod
    def add_scan(endpoint: Endpoint, rating: str, rating_no_trust: str, message: str, evidence: str=""):

        # Check if the latest scan has the same rating or not:
        try:
            gs = TlsScan.objects.all().filter(
                endpoint=endpoint,
            ).latest('last_scan_moment')
        except ObjectDoesNotExist:
            gs = TlsScan()

        # last scan had exactly the same result, so don't create a new scan and just update the
        # last scan date.
        if gs.explanation == message and gs.rating == rating and gs.rating_no_trust == rating_no_trust:
            logger.debug("Scan had the same rating and message, updating last_scan_moment only.")
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.save()
        else:
            # message and rating changed for this scan_type, so it's worth while to save the scan.
            logger.debug("Message or rating changed: making a new generic scan.")
            gs = TlsScan()
            gs.endpoint = endpoint
            gs.rating = rating
            gs.rating_no_trust = rating_no_trust
            gs.explanation = message
            gs.evidence = evidence
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.rating_determined_on = datetime.now(pytz.utc)
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
            gs = TlsScan.objects.all().filter(
                endpoint=endpoint,
            ).latest('last_scan_moment')
            if gs.rating:
                return True
        except ObjectDoesNotExist:
            return False
