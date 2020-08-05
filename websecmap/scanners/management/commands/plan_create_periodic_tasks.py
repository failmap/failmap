import json
import logging
from pprint import pprint

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule

from websecmap.scanners.scanner import (dnssec, ftp, security_headers, tls_qualys, plain_http, subdomains,
                                        dns_wildcards, dns_known_subdomains, dns_endpoints, http)

log = logging.getLogger(__name__)

intervals = {
    # daily
    "every day": 4,

    # every 10 minutes
    'every 10 minutes': 32,

    # every 5 minutes
    'every 5 minutes': 9,

    # every 5 days:
    'every 5 days': 7,

    # :
    'every 7 days': 10,

    'every 3 days': 11,
    'every 2 days': 35,
}


def plan_daily(scanner: str, method: str):
    return {'task': f'websecmap.scanners.{scanner}.plan_{method}',
            'cron': intervals["every day"],
            'friendly_name': f'{scanner} &#x2795 Plan {method} for scanner {scanner}',
            'args': "[]",
            'kwargs': "{}"
            }


def consume(scanner: str, method: str, interval: str, amount: int):
    return {'task': f'websecmap.app.models.create_{method}_job',
         'cron': intervals[interval],
         'friendly_name': f'{scanner} &#x1F52C; {method} using {scanner}.',
         'args': f'["websecmap.scanners.scanner.{scanner}"]',
         'kwargs': f'{{"amount": {amount}}'
         },

class Command(BaseCommand):
    """
    Generates periodic tasks, based on some rudimentary settings. These tasks replace the current
    discover tasks.

    Normally all scans are planned and executed using periodic tasks. This command however will plan
    all verify, discovery and scan tasks on the entire system.

    """

    task_name = "create_planned_scan_job, create_planned_verify_job, create_planned_discover_job"
    # todo: check if dns_endpoints can/should be refactored too. Probably, but there are external dependencies.
    regime = [
        # FTP, discover, scan and verify
        plan_daily('ftp', 'discover'),
        plan_daily('ftp', 'scan'),
        plan_daily('ftp', 'verify'),

        # processing tasks will do nothing if there is nothing planned. Just keep them running.
        # if they request too much stuff, the workers themselves will distribute / rate limit.
        consume('ftp', 'planned_scan', 'every 10 minutes', amount=100),
        consume('ftp', 'planned_verify', 'every 10 minutes', amount=25),
        consume('ftp', 'planned_discover', 'every 5 minutes', amount=200),

        # http endpoints, discover and verify

    ]

    def handle(self, *args, **options):
        # internet.nl v2 scanner has to be used in websecmap.
        for item in self.regime:

            if PeriodicTask.objects.all().filter(name=item['friendly_name']).exists():
                log.warning(f"Periodic task with {item['friendly_name']} already exists, removing.")
                PeriodicTask.objects.all().filter(name=item['friendly_name']).delete()
                continue

            new_task = PeriodicTask()
            new_task.name = item['friendly_name']
            new_task.task = item['task']
            new_task.crontab = CrontabSchedule.objects.filter(id=item['cron']).first()
            new_task.args = item['args']
            new_task.kwargs = item['kwargs']
            new_task.queue = "storage"
            new_task.enabled = False
            new_task.save()
            log.info(f"Created new task: {item['friendly_name']}")
