import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand

from .datasethelpers import check_referential_integrity

logger = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = "Create a near complete export for testing and migrating to another server."

    def handle(self, *app_labels, **options):
        """
        This function will make a YAML export of the data in the database that is not easily
        recreateable. Here is a list of what is and is not included.

                                Included
        Map:
        - Url Rating            No          Can be rebuild with rebuildratings
        - Organization Rating   No          Can be rebuild with rebuildratings

        Organization:
        - Coordinates           Yes         Hard to create, is not scripted yet
        - Organizations         Yes         Hard to gather
        - OrganizationType      Yes         Foreign Keys
        - Urls                  Yes         Even harder to gather

        Scanners:
        - Endpoints             Yes         Needed for rebuild ratings, hard to gather
        - Screenshots           No          Can be recreated with ease (except history)
        - States                No          Just start somewhere
        - TLS Qualys Scans      Yes         Needed for rebuild ratings
        - TLS Qualys Scratchpa  No          This is mainly for debugging (todo: check scan tls qual)
        - Generic Scans         Yes
        - Generic Scans scratch No

        Auth:
        - Users                 No          Create this yourself
        - Groups                No          Create this yourself

        Further docs:
        https://docs.djangoproject.com/en/1.11/ref/django-admin/
        https://stackoverflow.com/questions/20518341/django-dumpdata-from-a-python-script

        :param args:
        :param options:
        :return:
        """

        check_referential_integrity()

        filename = "failmap_dataset_{}.{options[format]}".format(
            datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S"),
            options=options
        )

        # Override default options.
        if not options['output']:
            options["output"] = filename

        # Fill the list of things to export
        if not app_labels:
            # about 8 megabyte
            app_labels = (
                "organizations.OrganizationType",
                "organizations.Organization",
                "organizations.Coordinate",
                "organizations.Url",
                "scanners.Endpoint",
                "scanners.TlsQualysScan",
                "scanners.EndpointGenericScan"
            )
            # the rest:
            # about 160 megabyte for the database
            # screenshot files are about 6 gigabyte
            # app_labels = ('organizations', 'scanners', 'map')  # to check size of whole database

        logger.debug(app_labels)
        logger.debug(options)

        super(Command, self).handle(*app_labels, **options)
