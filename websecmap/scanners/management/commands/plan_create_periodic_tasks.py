import logging

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask

log = logging.getLogger(__name__)

intervals = {
    'every 5 minutes': 9,
    'every 10 minutes': 32,
    'every 30 minutes': 33,

    "every day": 4,
    'every 2 days': 35,
    'every 3 days': 11,
    'every 5 days': 7,
    'every 7 days': 10,
}


def plan_daily(scanner: str, method: str, interval: str = "every day"):
    return {'task': f'websecmap.scanners.scanner.{scanner}.plan_{method}',
            'cron': intervals[interval],
            'friendly_name': f'{scanner}: {fitting_icon(method)}',
            'args': "[]",
            'kwargs': "{}"
            }


def consume(scanner: str, method: str, interval: str, amount: int):
    return {'task': f'websecmap.app.models.create_{method}_job',
            'cron': intervals[interval],
            'friendly_name': f'{scanner}: {fitting_icon(method)}',
            'args': f'["websecmap.scanners.scanner.{scanner}"]',
            'kwargs': f'{{"amount": {amount}}}'
            }


def fitting_icon(some_text):

    options = {
        'scan': 'Schedule Scan',
        'verify': 'Schedule Verification',
        'discover': 'Schedule Discovery',
        'planned_scan': 'Perform Scan',
        'planned_verify': 'Perform Verification',
        'planned_discover': 'Perform Discovery ',
    }

    return options[some_text]


class Command(BaseCommand):
    """
    Generates periodic tasks, based on some rudimentary settings. These tasks replace the current
    discover tasks.

    Normally all scans are planned and executed using periodic tasks. This command however will plan
    all verify, discovery and scan tasks on the entire system.

    """

    task_name = "create_planned_scan_job, create_planned_verify_job, create_planned_discover_job"
    # todo: check if dns_endpoints can/should be refactored too. Probably, but there are external dependencies.
    # todo: dns wildcards (is not used in automatided scans yet...), internet.nl v2 with dns_endpoints
    regime = [
        # FTP: discover, scan and verify
        plan_daily('ftp', 'discover', "every day"),
        plan_daily('ftp', 'scan', "every day"),
        plan_daily('ftp', 'verify', "every day"),

        # processing tasks will do nothing if there is nothing planned. Just keep them running.
        # if they request too much stuff, the workers themselves will distribute / rate limit.
        consume('ftp', 'planned_scan', 'every 10 minutes', amount=100),
        consume('ftp', 'planned_verify', 'every 10 minutes', amount=25),
        consume('ftp', 'planned_discover', 'every 5 minutes', amount=200),

        # http endpoints: discover and verify
        plan_daily('http', 'discover', "every 5 days"),
        plan_daily('http', 'verify', "every 2 days"),

        consume('http', 'planned_discover', 'every 5 minutes', amount=200),
        consume('http', 'planned_verify', 'every 5 minutes', amount=200),

        # dnssec: scan
        plan_daily('dnssec', 'scan', "every day"),
        consume('dnssec', 'planned_scan', 'every 10 minutes', amount=50),

        # plain_https: scan
        plan_daily('plain_http', 'scan', "every day"),
        consume('plain_http', 'planned_scan', 'every 10 minutes', amount=200),

        # subdomains: verify, discover
        plan_daily('subdomains', 'verify', "every 3 days"),
        plan_daily('subdomains', 'discover', "every 3 days"),
        consume('subdomains', 'planned_verify', 'every 10 minutes', amount=200),
        consume('subdomains', 'planned_discover', 'every 10 minutes', amount=200),

        # verify unresolvable
        plan_daily('verify_unresolvable', 'verify', "every 3 days"),
        consume('verify_unresolvable', 'planned_verify', 'every 10 minutes', amount=200),

        # tls qualys: scan
        plan_daily('tls_qualys', 'scan', "every 3 days"),
        consume('tls_qualys', 'planned_scan', 'every 10 minutes', amount=25),

        # http security headers
        plan_daily('security_headers', 'scan', "every day"),
        consume('security_headers', 'planned_scan', 'every 10 minutes', amount=200),

        # dns_endpoints: verify, discover
        plan_daily('dns_endpoints', 'verify', "every day"),
        plan_daily('dns_endpoints', 'discover', "every day"),
        consume('dns_endpoints', 'planned_verify', 'every 10 minutes', amount=200),
        consume('dns_endpoints', 'planned_discover', 'every 10 minutes', amount=200),

        # internet.nl v2: scan
        # add urls to the queue
        plan_daily('internet_nl_v2_mail', 'scan', "every 3 days"),
        plan_daily('internet_nl_v2_web', 'scan', "every 3 days"),
        # and then run a scan on them, as long as there are urls, per 500:
        consume('internet_nl_v2_mail', 'planned_scan', 'every 30 minutes', amount=500),
        consume('internet_nl_v2_web', 'planned_scan', 'every 30 minutes', amount=500),

        # known subdomains: discover
        # it's very intense as it tries a number of words per domain, so don't use it too often
        plan_daily('dns_known_subdomains', 'discover', "every 7 days"),
        consume('dns_known_subdomains', 'planned_discover', 'every 30 minutes', amount=25),

        # dns wildcards
        plan_daily('dns_wildcards', 'discover', "every 3 days"),
        consume('dns_wildcards', 'planned_discover', 'every 10 minutes', amount=200),

        # screenshots
        plan_daily('screenshot', 'scan', "every 7 days"),
        consume('screenshot', 'planned_scan', 'every 30 minutes', amount=25),
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
