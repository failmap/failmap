from django.core.management.base import BaseCommand
import redis
import json
from django.conf import settings
import logging

log = logging.getLogger(__name__)


class Command(BaseCommand):
    "Revoke tasks from queue"

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("queue", nargs=1, type=str, help="Queue to remove tasks from")
        parser.add_argument(
            "task_name",
            nargs=1,
            type=str,
            help=(
                "Name of the task to remove (full import path, "
                "eg: websecmap.scanners.scanner.autoexplain_dane_microsoft.correct_scan"
            ),
        )
        super().add_arguments(parser)

    def handle(self, *args, **options):
        queue = options["queue"][0]
        revoke_task_name = options["task_name"][0]

        r = redis.Redis.from_url(settings.CELERY_BROKER_URL)

        total_tasks = r.llen(queue)
        task_count = 0
        revoked_count = 0

        while task_count < total_tasks:
            task = r.lpop(queue)

            if not task:
                continue

            task_count += 1
            task_headers = json.loads(task)["headers"]
            task_name = task_headers["task"]
            if task_name == revoke_task_name:
                print("x", end="", flush=True)
                revoked_count += 1
            else:
                print(".", end="", flush=True)
                r.rpush(queue, task)

        print()
        print(f"{task_count} tasks, {revoked_count} revoked")
