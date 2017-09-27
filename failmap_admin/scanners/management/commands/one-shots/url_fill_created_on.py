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
        urls = Url.objects.all().filter()
        # created_on__isnull=True = 780 hits...
        # manually checking: if not url.created_on == 3084. HOW!?

        logger.debug("Urls that don't have a created on: %s" % urls.count())
        # the earliest creation date = the creation date of the oldest endpoint
        for url in urls:

            if not url.created_on:
                try:
                    oldest_endpoint = Endpoint.objects.all().filter(
                        url=url).earliest('discovered_on')
                    logger.debug("The oldest endpoint for url: %s is: %s" %
                                 (url, oldest_endpoint.discovered_on))
                    url.created_on = oldest_endpoint.discovered_on
                    url.save()
                except ObjectDoesNotExist:
                    logger.warning("Creation date for url could not be determined: %s" % url)
