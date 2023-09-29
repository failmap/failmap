from websecmap.app.management.commands._private import TaskCommand
from websecmap.celery import app


# don't know if the taskcommand stuff clashes
class Command(TaskCommand):
    def add_arguments(self, parser):
        parser.add_argument("task", nargs=1, help="The task to run. Use 'task_list' for a list of possble tasks.")
        super().add_arguments(parser)

    def compose(self, *args, **options):
        return app.tasks[options["task"][0]]
