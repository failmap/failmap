import logging

from websecmap.app.management.commands._private import DiscoverTaskCommand
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner.tls_qualys import check_proxy

log = logging.getLogger(__name__)


class Command(DiscoverTaskCommand):
    """Checks a specific proxy by ID. When no ID is given, all proxies are checked."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            proxies = ScanProxy.objects.all()
            for proxy in proxies:
                log.info(f'Checking proxy {proxy}.')
                check_proxy(proxy)

        except KeyboardInterrupt:
            log.info("Stopped checking proxy.")
