import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.duplicates import deduplicate_all_endpoints_sequentially

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Removes duplicate endpoints.

    Duplicates can be created in case of dns outages. In that case endpoints are set to deleted and
    created afterwards when the dns is restored. In that case, a manual action may lead to "restoring"
    of the database, but in reality a set of queued "new endpoints" will also be created: so both
    the system created endpoints and the administrator made alive endpoints.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", nargs=1, help="How big the gap between endpoints can be, default=60", type=int, default=60
        )
        super().add_arguments(parser)

    help = __doc__

    def handle(self, *args, **options):
        deduplicate_all_endpoints_sequentially(days=options["days"])
