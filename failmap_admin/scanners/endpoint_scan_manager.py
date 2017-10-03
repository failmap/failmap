from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist


class EndpointScanManager:
    """
    Helps with data deduplication of scans. Helps storing scans in a more generic way.

    :return:
    """
    @staticmethod
    def add_scan(scantype, endpoint, rating, message):
        from .models import EndpointGenericScan

        # Check if the latest scan has the same rating or not:
        try:
            gs = EndpointGenericScan.objects.all().filter(
                type=scantype,
                endpoint=endpoint,
            ).latest('last_scan_moment')
        except ObjectDoesNotExist:
            gs = EndpointGenericScan()

        # last scan had exactly the same result, so don't create a new scan and just update the
        # last scan date.
        if gs.explanation == message and gs.rating == rating:
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.save()
        else:
            # make a new one, please don't update the existing one :)
            gs = EndpointGenericScan()
            gs.explanation = message
            gs.rating = rating
            gs.endpoint = endpoint
            gs.type = scantype
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.rating_determined_on = datetime.now(pytz.utc)
            gs.save()

    @staticmethod
    def had_scan_with_points(scantype, endpoint):
        """
        Used for data deduplication. Don't save a scan that had zero points, but you can upgrade
        to zero (or another rating)
        :param scantype:
        :param endpoint:
        :return:
        """
        from .models import EndpointGenericScan

        try:
            gs = EndpointGenericScan.objects.all().filter(
                type=scantype,
                endpoint=endpoint,
            ).latest('last_scan_moment')
            if gs.rating:
                return True
        except ObjectDoesNotExist:
            return False
