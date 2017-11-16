import logging

from failmap_admin.app.management.commands._private import TaskCommand

from ...determineratings import rebuild_ratings

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    task = rebuild_ratings
