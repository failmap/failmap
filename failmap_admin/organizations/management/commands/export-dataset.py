import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand
from django.db import connection

from failmap_admin import settings

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

        # first check if there are reference issues. If there are, then we can't export.
        # They must be fixed, otherwise
        # we can't loaddata at a later stage without terrible hacks.

        # this only works for ssqlite.
        if "sqlite" in settings.DATABASES["default"]["ENGINE"]:
            # http://www.sqlite.org/pragma.html#pragma_foreign_key_check
            logger.info(
                'Checking for foreign key issues, and generating possible SQL to remediate issues.')

            cursor = connection.cursor()
            cursor.execute('''PRAGMA foreign_key_check;''')
            rows = cursor.fetchall()
            if rows:
                logger.error("Cannot create export. There are incomplete foreign keys. "
                             "See information above to fix this. "
                             "Please fix these issues manually and try again.")

            for row in rows:
                logger.info("%25s %6s %25s %6s" % (row[0], row[1], row[2], row[3]))

            logger.error(
                "Here are some extremely crude SQL statements that might help fix the problem.")
            for row in rows:
                logger.info("DELETE FROM %s WHERE id = \"%s\";" % (row[0], row[1]))

            if rows:
                return
        else:
            logger.warning("This export might have incorrect integrity: no foreign key check for "
                           "this engine was implemented. Loaddata might not accept this import. "
                           "Perform a key check manually.")
            return

        filename = "failmap_dataset_%s.yaml" % datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S")

        # Override default options.
        options["indent"] = 2
        options["format"] = "yaml"
        options["output"] = filename
        options["verbosity"] = 1  # Show progress bar, it's not really helpful though :)

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
