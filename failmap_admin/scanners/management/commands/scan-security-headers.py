import json
import logging

from failmap_admin.app.management.commands._private import TaskCommand
from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.scanner_security_headers import compose_scan_organizations

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    def _add_arguments(self, parser):
        """Add command specific arguments."""
        self.mutual_group.add_argument('-o', '--organizations', nargs='*',
                                       help="Perform scans on these organizations (default is all).")

    def compose(self, *args, **options):
        """Compose set of tasks based on provided arguments."""

        # select specified or all organizations to be scanned
        if options['organizations']:
            organizations = list()
            for organization_name in options['organizations']:
                try:
                    organizations.append(Organization.objects.get(name__iexact=organization_name))
                except Organization.DoesNotExist as e:
                    raise Exception("Failed to find organization '%s' by name" % organization_name) from e
        else:
            organizations = Organization.objects.all()

        # compose set of tasks to be executed
        return compose_scan_organizations(organizations)
