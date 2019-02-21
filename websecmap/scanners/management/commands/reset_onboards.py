import logging

from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.organizations.models import Url
from websecmap.scanners.scanner.onboard import reset_onboarding_status

log = logging.getLogger(__name__)


class Command(VerifyTaskCommand):
    """Sets the unfinished onboarding step of not fully onboarded urls to a previous one. Will not run finished
    onboarding steps again. You can run this if urls are not progressing with onboarding, all queues are empty and
    you don't want to wait 7 days until onboards have expired. This feature does not have filter options. It will reset
    for all urls in the database that have an unfinished unboarding step. Unfinished onboarding steps are:
    endpoint_discovery, scans_running and crawl_started."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            expired = Url.objects.all().filter(onboarding_stage__in=['endpoint_discovery', 'scans_running',
                                                                     'crawling'])

            for url in expired:
                log.debug("Resetting onboarding status of %s" % url)
                reset_onboarding_status(url)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
