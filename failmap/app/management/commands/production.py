from ._private import RunWrapper


class Command(RunWrapper):
    """Run a Failmap production server."""

    command = 'runuwsgi'
