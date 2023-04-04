import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.chatgpt_metadata import chatgpt_hello, chatgpt_thank_you, enrich_product_metadata

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        try:
            chatgpt_hello()
            while True:
                enrich_product_metadata()
        except KeyboardInterrupt:
            chatgpt_thank_you()
            print("Done.")
