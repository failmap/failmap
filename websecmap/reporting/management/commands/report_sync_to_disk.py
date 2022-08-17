import logging

from django.core.management import BaseCommand

from websecmap.map.models import OrganizationReport
from websecmap.reporting.diskreport import get_original_storage_location, sync_reports_from_db_to_disk

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Syncs existing reports to disk. Example: --limit=10"""

    # todo: add parameter

    help = __doc__

    def add_arguments(self, parser):

        parser.add_argument(
            "--limit",
            type=int,
            help="Number of reports to sync to disk (large bat ches will crash)",
            required=False,
            default=100,
        )

    def handle(self, *args, **options):
        print(f"Syncing reports to: {get_original_storage_location()}.")
        print("This can take a while...")

        limit = 1000000
        if "limit" in options:
            limit = int(options["limit"])

        sync_reports_from_db_to_disk(OrganizationReport, limit)

        print("Don't forget to optimize tables afterwards otherwise disk space is not reclaimed.")
