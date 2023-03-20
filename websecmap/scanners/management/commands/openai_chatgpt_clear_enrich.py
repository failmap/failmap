import logging

from django.core.management.base import BaseCommand

# from websecmap.scanners.chatgpt_metadata import clear_enrichment

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        ...
        # clear_enrichment()
