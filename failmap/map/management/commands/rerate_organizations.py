import logging

from failmap.app.management.commands._private import TaskCommand

from ...rating import rerate_organizations

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    task = rerate_organizations
