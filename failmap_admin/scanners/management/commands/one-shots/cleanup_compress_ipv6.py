import ipaddress
import logging

import tldextract
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Endpoint, TlsQualysScan, Url

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Compress IPv6 addresses in the database.'

    """
    It should only be needed to run this script once when upgrading from very early versions
    of faalkaart. You probably don't need to run this anymore...
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        endpoints = Endpoint.objects.all()

        for endpoint in endpoints:
            compressed = ipaddress.ip_address(endpoint.ip).compressed
            if compressed != endpoint.ip:
                logging.debug("Endpoint %s" % endpoint)
                logging.debug("Compressed %s to %s. Saving." % (endpoint.ip, compressed))
                endpoint.ip = compressed
                endpoint.save()
