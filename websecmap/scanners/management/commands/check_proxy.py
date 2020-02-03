import logging

from websecmap.app.management.commands._private import DiscoverTaskCommand
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner.tls_qualys import check_proxy

log = logging.getLogger(__name__)


class Command(DiscoverTaskCommand):
    """Checks a specific proxy by ID. When no ID is given, all proxies are checked."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('id', nargs=1)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            proxy = ScanProxy.objects.all().filter(id=options['id'][0]).first()
            check_proxy(proxy)

        except KeyboardInterrupt:
            log.info("Stopped checking proxy.")
