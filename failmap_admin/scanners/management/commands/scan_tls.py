import logging

from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_tls import test_real

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Scan websites for TLS and grade them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--url', '-u',
            nargs=1,
        )

        parser.add_argument(
            '--port', '-p',
            nargs=1,
        )

    def handle(self, *args, **options):

        if options['url']:
            if not options['port']:
                options['port'] = [443]

            logger.debug('%s:%s' % (options['url'][0], options['port'][0]))
            test_real(options['url'][0], options['port'][0])
