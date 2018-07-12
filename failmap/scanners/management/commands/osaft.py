import logging

from django.core.management.base import BaseCommand

from failmap.scanners.scanner_tls_osaft import (ammend_unsuported_issues, determine_grade,
                                                grade_report, run_osaft_scan)

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        address = "faalkaart.nl"
        port = 443
        report = run_osaft_scan(address, port)
        report = ammend_unsuported_issues(report, address, port)
        grades, trust, report = determine_grade(report)
        print(grade_report(grades, trust, report))
