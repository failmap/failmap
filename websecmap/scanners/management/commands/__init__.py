from websecmap.app import log
from websecmap.app.management.commands._private import TaskCommand


class ActionCommand(TaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = str(__doc__)

    scanners = {}

    def handle(self, *args, **options):
        try:
            scanner_name = options["scanner"][0]
            if scanner_name not in self.scanners:
                scanners = ", ".join(self.scanners.keys())
                return f"Scanner does not exist. Please specify a scanner: {scanners}"

            self.scanner_module = self.scanners[scanner_name]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")

        return ""
