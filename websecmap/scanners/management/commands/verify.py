from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.scanners import tasks
from websecmap.scanners.management.commands import ActionCommand


# don't know if the taskcommand stuff clashes
class Command(VerifyTaskCommand, ActionCommand):
    scanners = {x.__name__.split(".")[-1]: x for x in tasks.__scanners__ if hasattr(x, "compose_manual_verify_task")}
