import json
import logging

from failmap_admin.app.management.commands._private import TaskCommand
from failmap_admin.scanners.scanner_dummy_dumdum import scan

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Demostrative NOOP scanner for example purposes."""

    help = __doc__

    def _add_arguments(self, parser):
        """Add command specific arguments."""
        self.mutual_group.add_argument('-o', '--organization_names', nargs='*',
                                       help="Perform scans on these organizations (default is all).")

    def compose(self, *args, **options):
        """Compose set of tasks based on provided arguments."""

        # compose set of tasks to be executed
        return scan(options['organization_names'], execute=False)
