import logging

from django.core.management.base import BaseCommand

from failmap.scanners.scanner.tls_osaft import (ammend_unsuported_issues, cert_chain_is_complete,
                                                determine_grade, grade_report, run_osaft_scan)

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        cert_chain_is_complete("tweakers.net", 443)

        address = "tweakers.net"
        port = 443
        report = run_osaft_scan(address, port)
        report = ammend_unsuported_issues(report, address, port)
        grades, trust, report = determine_grade(report)
        print("report:")
        print(grade_report(grades, trust, report))
        # store_grade((grades, trust, report), )
