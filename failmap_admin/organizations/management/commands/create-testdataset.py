import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand
from django.core.serializers import serialize
from django.db import connection

from failmap_admin import settings
from failmap_admin.organizations.models import Coordinate, Organization, OrganizationType, Url
from failmap_admin.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan

logger = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = "Create a near complete export for testing and migrating to another server."

    def handle(self, *app_labels, **options):
        """
        This function will make a YAML testdata export of the data in the database that is not
        easily recreateable. Django's own serializers are used.

        Only organizations with the letter A will be included. This consists of large and small
        organizations. At max 10 organizations.

                                Included
        Organization:
        - OrganizationType      Yes         Foreign Keys
        - Organizations         Yes         Hard to gather
        - Coordinates           Yes         Hard to create, is not scripted yet
        - Urls                  Yes         Even harder to gather

        Scanners:
        - Endpoints             Yes         Needed for rebuild ratings, hard to gather
        - TLS Qualys Scans      Yes         Needed for rebuild ratings
        - Generic Scans         Yes
        """
        filename = "failmap_testdataset_%s.yaml" % datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S")

        file = open(filename, "w")

        file.write(serialize('yaml', OrganizationType.objects.all()))

        organizations = Organization.objects.all().filter(name__istartswith='A')[0:20]
        file.write(serialize('yaml', organizations))

        coordinates = Coordinate.objects.all().filter(organization__in=organizations)
        file.write(serialize('yaml', coordinates))

        urls = Url.objects.all().filter(organization__in=organizations)
        file.write(serialize('yaml', urls))

        endpoints = Endpoint.objects.all().filter(url__in=urls)
        file.write(serialize('yaml', endpoints))

        tlsqualysscans = TlsQualysScan.objects.all().filter(endpoint__in=endpoints)
        file.write(serialize('yaml', tlsqualysscans))

        endpointgenericscans = EndpointGenericScan.objects.all().filter(endpoint__in=endpoints)
        file.write(serialize('yaml', endpointgenericscans))

        file.close()
