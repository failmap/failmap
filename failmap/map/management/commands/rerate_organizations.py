import logging

from failmap.app.management.commands._private import TaskCommand

from ...report import rebuild_organization_ratings

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    task = rebuild_organization_ratings
