import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.export_metrics import export_pivot

log = logging.getLogger(__name__)


class Command(BaseCommand):
    # a metric on all layers
    # websecmap export_pivot web_privacy_cookies
    # a metric on specific layers
    # websecmap export_pivot web_privacy_cookies government municipality
    # Exporting pivot for: ['web_privacy_cookies'] on layers: ['government', 'municipality']
    def add_arguments(self, parser):
        parser.add_argument("scan_type", nargs=1)
        super().add_arguments(parser)

        parser.add_argument("layers", nargs="*")
        super().add_arguments(parser)

    def handle(self, *args, **options):
        scan_type = options.get("scan_type")
        if scan_type is None:
            print("Please specify a scan type")
            return

        layers = options.get("layers")
        if layers is None:
            print("Will export all layers.")
            return

        print(f"Exporting pivot for: {scan_type[0]} on layers: {layers}")
        filename = export_pivot(scan_type, layers=layers)
        print(f"Exported pivot to: {filename}")
        print("Done")
