import logging

from celery import group

from websecmap.app.management.commands._private import TaskCommand
from websecmap.scanners.scanner import (
    dns_wildcards,
    dnssec,
    ftp,
    http,
    plain_http,
    security_headers,
    subdomains,
    tls_qualys,
    verify_unresolvable,
)

log = logging.getLogger(__name__)


class Command(TaskCommand):
    """
    Consume random items in the planned scan list, to influence the progress bar. Used to develop that
    progress bar.
    """

    def compose(self, *args, **options):
        scanners = [
            dnssec,
            ftp,
            http,
            dns_wildcards,
            plain_http,
            security_headers,
            subdomains,
            tls_qualys,
            verify_unresolvable,
        ]

        tasks = []
        for scanner in scanners:
            if getattr(scanner, "compose_planned_discover_task", None):
                tasks.append(scanner.compose_planned_discover_task(amount=1))

            if getattr(scanner, "compose_planned_verify_task", None):
                tasks.append(scanner.compose_planned_verify_task(amount=1))

            if getattr(scanner, "compose_planned_scan_task", None):
                tasks.append(scanner.compose_planned_scan_task(amount=1))

        return group(tasks)
