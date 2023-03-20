import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.chatgpt_metadata import chatgpt_get_product_vendor, chatgpt_thank_you

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("The following should yield something like 'Atlassian'.")
        print(chatgpt_get_product_vendor("Confluence"))
        print(chatgpt_thank_you())
