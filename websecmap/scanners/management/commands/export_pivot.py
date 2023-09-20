import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.export_metrics import export_pivot

log = logging.getLogger(__name__)


class Command(BaseCommand):
    # arguments: scan type as a string:
    def add_arguments(self, parser):
        parser.add_argument("stan_type", nargs="?")
        super().add_arguments(parser)

    def handle(self, *args, **options):
        scan_type = options.get("stan_type")
        if scan_type is None:
            print("Please specify a scan type")
            return

        print(f"Exporting pivot for: {scan_type}")
        filename = export_pivot([scan_type])
        print(f"Exported pivot to: {filename}")
        print("Done")
