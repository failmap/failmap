import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand
from django.core.serializers import serialize

from failmap.organizations.models import Coordinate, Organization, OrganizationType, Promise, Url
from failmap.scanners.models import Endpoint, EndpointGenericScan, UrlIp

log = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = "The test-dataset exports 20 organizations, with their minimal information such as scans. Log info" \
           "will not be attached."

    FILENAME = "failmap_test_dataset_{}.{options[format]}"

    APP_LABELS = ('organizations', 'scanners', 'map', 'django_celery_beat')

    # for testing it is nice to have a human editable serialization language
    FORMAT = 'yaml'

    def add_arguments(self, parser):
        """Add arguments."""
        parser.add_argument('-c', '--count', default=20, type=int,
                            help='Maximum amount of organization to create in the dataset.')
        super(Command, self).add_arguments(parser)

    def handle(self, *app_labels, **options):
        """
        This function will make a YAML testdata export of the data in the database that is not
        easily recreateable. Django's own serializers are used.

        Only organizations with the letter A will be included. This consists of large and small
        organizations. At max 20 organizations.

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

        # force desired format for testing
        options['format'] = self.FORMAT

        if options['output']:
            filename = options['output']
        else:
            # generate unique filename for every export
            filename = self.FILENAME.format(
                datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S"),
                options=options
            )

        objects = []

        objects += OrganizationType.objects.all()

        organizations = Organization.objects.all().filter(name__istartswith='A')[0:options['count']]
        objects += organizations

        coordinates = Coordinate.objects.all().filter(organization__in=organizations)
        objects += coordinates

        urls = Url.objects.all().filter(organization__in=organizations)
        objects += urls

        endpoints = Endpoint.objects.all().filter(url__in=urls)
        objects += endpoints

        endpointgenericscans = EndpointGenericScan.objects.all().filter(endpoint__in=endpoints)
        objects += endpointgenericscans

        promises = Promise.objects.all().filter(organization__in=organizations)
        objects += promises

        urlips = UrlIp.objects.all().filter(url__in=urls)
        objects += urlips

        with open(filename, "w") as f:
            f.write(serialize(self.FORMAT, objects))

        log.info('Wrote %s', filename)
