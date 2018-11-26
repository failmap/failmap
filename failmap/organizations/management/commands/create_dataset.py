import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand

from failmap.organizations.management.commands.support.datasethelpers import \
    check_referential_integrity

log = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = "A dataset that is free of things that are easy to recreate. Such things are all logs from scanners," \
           "screenshots and such."

    FILENAME = "failmap_dataset_{}.{options[format]}"

    # Here is a list of what is and is not included.
    #
    #                                 Included
    #         Map:
    #         - Url Rating            No          Can be rebuild with rebuildratings
    #         - Organization Rating   No          Can be rebuild with rebuildratings
    #
    #         Organization:
    #         - Coordinates           Yes         Hard to create, is not scripted yet
    #         - Organizations         Yes         Hard to gather
    #         - OrganizationType      Yes         Foreign Keys
    #         - Urls                  Yes         Even harder to gather
    #         - Promises              Yes         Might contain valuable data
    #
    #         Scanners:
    #         - Endpoints             Yes         Needed for rebuild ratings, hard to gather
    #         - Screenshots           No          Can be recreated with ease (except history)
    #         - TLS Scans             Yes
    #         - TLS Qualys Scans      Yes         Needed for rebuild ratings
    #         - TLS Qualys Scratchpa  No          This is mainly for debugging
    #         - Generic Scans         Yes
    #         - Generic Scans scratch No
    #         - UrlIp                 Yes         Might contain valuable data
    #
    #         Auth:
    #         - Users                 No          Create this yourself
    #         - Groups                No          Create this yourself
    #
    #         Game:
    #         - Team                  Yes
    #         - Contest               Yes
    #         - OrganizationSubmission Yes        Helps with debugging
    #         - UrlSubmission         Yes         Helps with debugging

    APP_LABELS = (
        "organizations.OrganizationType",
        "organizations.Organization",
        "organizations.Coordinate",
        "organizations.Url",
        "organizations.Promise",
        "scanners.Endpoint",
        "scanners.TlsScan",
        "scanners.EndpointGenericScan",
        "scanners.UrlGenericScan",
        "scanners.UrlIp",
        "map.Configuration",
        "map.AdministrativeRegion",
        "game",
        "hypersh",
        "django_celery_beat"
    )

    def handle(self, *app_labels, **options):
        """
        This function will make a YAML export of the data in the database that is not easily
        recreateable.

        Further docs:
        https://docs.djangoproject.com/en/1.11/ref/django-admin/
        https://stackoverflow.com/questions/20518341/django-dumpdata-from-a-python-script

        :param args:
        :param options:
        :return:
        """

        # verify data is properly exportable
        check_referential_integrity()

        # generate unique filename for every export
        filename = self.FILENAME.format(
            datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S"),
            options=options
        )

        # if no output specified use default file
        if not options['output']:
            options["output"] = filename
        # allow to output to stdout to enable gzip compression if needed
        if options['output'] == '-':
            options['output'] = None

        # unless specified on the commandline, use default set of apps to export
        if not app_labels:
            app_labels = self.APP_LABELS

        super(Command, self).handle(*app_labels, **options)
