import logging

from django.core.management import BaseCommand

from websecmap.scanners.models import ScanProxy
from websecmap.scanners.proxy import check_all_proxies, check_proxy

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Checks a specific proxy by ID. When no ID is given, all proxies are checked."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("id", nargs="?")
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options["id"]:
                for id in options["id"]:
                    proxy = ScanProxy.objects.all().filter(id=id).first()
                    if proxy:
                        check_proxy(proxy)
            else:
                check_all_proxies()

        except KeyboardInterrupt:
            log.info("Stopped checking proxy.")
