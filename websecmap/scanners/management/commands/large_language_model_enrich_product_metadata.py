import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.large_language_model_product_metadata import enrich_product_metadata, llm_hello, llm_thank_you

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        try:
            llm_hello()
            while True:
                enrich_product_metadata()
        except KeyboardInterrupt:
            llm_thank_you()
            print("Done.")
