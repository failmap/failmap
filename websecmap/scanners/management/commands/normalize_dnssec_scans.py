import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner.dnssec import normalize_existing_dnssec_scans

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = (
        "DNSSEC scan evidence was not normalized, therefore a lot of duplicate data was stored in the database"
        " everything stuff was scanned. This normalizes those evidence records so the duplicates can be deduped."
    )

    def handle(self, *args, **options):
        normalize_existing_dnssec_scans()
