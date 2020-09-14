import logging

from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.organizations.models import Url
from websecmap.scanners.scanner.onboard import forward_onboarding_status

log = logging.getLogger(__name__)


class Command(VerifyTaskCommand):
    """This forwards the current onboarding states to a finished state."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            expired = Url.objects.all().filter(onboarding_stage__in=["endpoint_discovery", "scans_running", "crawling"])

            for url in expired:
                log.debug("Forwarding onboarding status of %s" % url)
                forward_onboarding_status(url)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
