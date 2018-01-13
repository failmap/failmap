import logging

from failmap.app.management.commands._private import TaskCommand
from failmap.scanners import scanner_dummy

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

        if not options['organization_names']:
            # by default no filter means all organizations
            organization_filter = dict()
        else:
            # create a case-insensitive filter to match organizations by name
            regex = '^(' + '|'.join(options['organization_names']) + ')$'
            organization_filter = {'name__iregex': regex}

        # compose set of tasks to be executed
        return scanner_dummy.create_task(organization_filter)
