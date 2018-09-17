from failmap.app.management.commands._private import ScannerTaskCommand

from ... import rating


class Command(ScannerTaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    def handle(self, *args, **options):
        self.scanner_module = rating
        return super().handle(self, *args, **options)
