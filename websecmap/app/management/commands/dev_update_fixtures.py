import sys
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    # This assumes that what you have in the development database is correct.
    # Therefore this should be handled with (some) caution.
    """Dump useful data from database to the shipped application. Only export data from a 'shipping-ready' database."""

    help = __doc__

    def handle(self, *args, **options):
        """
        This fixture is a workaround to enable users to enable and disable scanners using the constance admin
        webinterface.
        It is also used for rate limits. These constance variables are loaded at bootstrap of the application, before
        the database is run. It is by design that database access is not available when declaring constance variables.

        Thus the database is written to a file, the file is loaded up at boot and the settings are created. Every time
        one of the below models is changed, a constance_definitions.json file is dumped to disk to a writable directory.

        This fixture makes it possible to use this same database in tests.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/scanners/fixtures/scanmetadata.json", 'wt')
        call_command(
            "dumpdata",
            "scanners.scanner",
            "scanners.scantype",
            "scanners.scantypesecondopinionlink",
            "scanners.scantypedocumentationlink",
            "scanners.scantypecategory",
            "scanners.scanneractivity",
        )
        sys.stdout = sysout

        """
        ScanPolicy is a summary of all possible results of all scans types.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/reporting/fixtures/default_policy.json", 'wt')
        call_command("dumpdata", "reporting.scanpolicy"),
        sys.stdout = sysout

        """
        Periodic tasks like scanning and such are handled in celery beat.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/app/fixtures/periodic_tasks.json", 'wt')
        call_command("dumpdata", "django_celery_beat")
        sys.stdout = sysout
