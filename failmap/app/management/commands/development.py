from ._private import RunWrapper


class Command(RunWrapper):
    """Run a Failmap development server."""

    command = 'runserver'
