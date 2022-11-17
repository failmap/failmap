import logging

from django.core.management.base import BaseCommand

from websecmap.app.management.commands._private import apply_log_verbosity
from websecmap.scanners import plannedscan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            help="How many minutes you want to go back to evaluate the need of adding" " follow up scans.",
            type=int,
            default=60,
        )
        super().add_arguments(parser)

    def handle(self, *args, **options):
        apply_log_verbosity({"verbosity": 2})

        plannedscan.plan_follow_up_scans(amount_of_minutes_of_scan_history=options.get("minutes", 60))
