import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.autoexplain import autoexplain_trust_microsoft

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Finds a maximum of 50 scan proxies for you to work with, if you don't roll your own."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            autoexplain_trust_microsoft()
            log.info("Autoexplain finished!")

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
