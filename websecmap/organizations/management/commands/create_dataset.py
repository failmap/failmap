import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand

from websecmap.organizations.management.commands.support.datasethelpers import check_referential_integrity

log = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = (
        "A dataset that is free of things that are easy to recreate. Such things are all logs from scanners,"
        "screenshots and such."
    )

    FILENAME = "websecmap_dataset_{}.{options[format]}"

    APP_LABELS = (
        "organizations.OrganizationType",
        "organizations.Organization",
        "organizations.Coordinate",
        "organizations.Url",
        "organizations.Dataset",
        "scanners.Endpoint",
        "scanners.EndpointGenericScan",
        "scanners.UrlGenericScan",
        "scanners.InternetNLV2Scan",
        "scanners.InternetNLV2StateLog",
        "scanners.ScanProxy",
        "scanners.PlannedScan",
        "map.Configuration",
        "map.AdministrativeRegion",
        "map.LandingPage",
        "api",
        # game
        "game",
        # settings
        "constance",
        # planned tasks
        "django_celery_beat",
    )

    def handle(self, *app_labels, **options):
        """
        This function will make a JSON export of the data in the database that is not easily
        recreateable.

        Further docs:
        https://docs.djangoproject.com/en/1.11/ref/django-admin/
        https://stackoverflow.com/questions/20518341/django-dumpdata-from-a-python-script

        :param app_labels:
        :param options:
        :return:
        """

        # verify data is properly exportable
        check_referential_integrity()

        # generate unique filename for every export
        filename = self.FILENAME.format(datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S"), options=options)

        # if no output specified use default file
        if not options["output"]:
            options["output"] = filename
        # allow to output to stdout to enable gzip compression if needed
        if options["output"] == "-":
            options["output"] = None

        # unless specified on the commandline, use default set of apps to export
        if not app_labels:
            app_labels = self.APP_LABELS

        super(Command, self).handle(*app_labels, **options)
