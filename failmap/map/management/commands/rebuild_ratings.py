import logging

from failmap.app.management.commands._private import TaskCommand

from ...rating import rebuild_ratings_async

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    # 6.5 minutes
    # original: 1 hour
    task = rebuild_ratings_async
