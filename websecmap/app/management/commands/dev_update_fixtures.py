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
        These fixtures are shipped with the default product. Be sure to know that your database is fully OK before
        committing changes to these files!

        This fixture makes it possible to use this same database in tests.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/scanners/fixtures/scanmetadata.json", "wt")
        call_command(
            "dumpdata",
            "scanners.scantypesecondopinionlink",
            "scanners.scantypedocumentationlink",
            "scanners.scanneractivity",
            "scanners.scantypecategory",
            "scanners.scantype",
            "scanners.scanner",
            "scanners.followupscan",
            "--indent",
            2,
        )
        sys.stdout = sysout

        """
        ScanPolicy is a summary of all possible results of all scans types.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/reporting/fixtures/default_policy.json", "wt")
        call_command("dumpdata", "reporting.scanpolicy", "--indent", 2),
        sys.stdout = sysout

        """
        Periodic tasks like scanning and such are handled in celery beat.
        """
        sysout = sys.stdout
        sys.stdout = open("websecmap/app/fixtures/periodic_tasks.json", "wt")
        call_command("dumpdata", "django_celery_beat", "--indent", 2)
        sys.stdout = sysout
