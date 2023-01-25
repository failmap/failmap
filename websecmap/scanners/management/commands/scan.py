import logging

from websecmap.app.management.commands._private import ScannerTaskCommand
from websecmap.scanners import tasks

log = logging.getLogger(__name__)

scanners = {x.__name__.split(".")[-1]: x for x in tasks.__scanners__ if hasattr(x, "compose_manual_scan_task")}


class Command(ScannerTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("scanner", nargs=1, help="The scanner you want to use.", choices=scanners)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options["scanner"][0] not in scanners:
                print(f"Scanner does not exist. Please specify a scanner: {scanners.keys()} ")
                return

            self.scanner_module = scanners[options["scanner"][0]]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
