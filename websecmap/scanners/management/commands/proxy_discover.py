import logging

from django.core.management.base import BaseCommand

import websecmap.scanners.proxy

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Finds a maximum of 50 scan proxies for you to work with, if you don't roll your own."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--amount", help="amount", nargs='?', type=int, const=1, default=100)

        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            websecmap.scanners.proxy.find(amount=options['amount'])

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
