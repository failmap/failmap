from failmap.app.management.commands._private import TaskCommand

from ...rating import compose_task


class Command(TaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch."""

    help = __doc__

    task = compose_task()
