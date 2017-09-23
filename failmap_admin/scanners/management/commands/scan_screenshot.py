import logging
from datetime import datetime, timedelta
from time import sleep

import pytz
from django.core.management.base import BaseCommand
from django.db.models import Q

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_screenshot import ScannerScreenshot

logger = logging.getLogger(__package__)


# todo: when tls scanner ends, it hangs.
# Only the latest ratings...
class Command(BaseCommand):
    help = 'Create a screenshot'

    def handle(self, *args, **options):
        try:
            while True:
                Command.make_new_screenshots()
                logger.debug("Sleeping for half a day.")
                sleep(43200)  # sleep half a day
        except KeyboardInterrupt:
            logger.debug("ALL DONE!")

    @staticmethod
    def make_new_screenshots():
        s = ScannerScreenshot()

        one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

        # never had a screenshot or only has screenshots older than a month
        no_screenshots = Endpoint.objects.all().filter(is_dead=False,
                                            url__not_resolvable=False,
                                            screenshot__isnull=True)
        outdated_screenshots = Endpoint.objects.all().filter(is_dead=False,
                                            url__not_resolvable=False,
                                             screenshot__created_on__lt=one_month_ago)
        endpoints = list(no_screenshots) + list(outdated_screenshots)

        logger.debug("Found endpoints %s" % len(endpoints))

        # Chrome headless, albeit single threaded, is pretty reliable and fast for existing
        # domains. This code is also the most updated. Waiting for firefox with screenshot
        # support. (they use --screenshot=<path>, so that might work multithreaded)
        # when only visiting existing domains (no timeouts) you'll have about 21 screenshots
        # per minute. Which is pretty ok.
        # todo: have a timeout of max N seconds per screenshot. Chrome doesn't have that.
        # killing python process might result in a random chrome process staying alive.

        # Warning: opening a browser might also mean it wants to play audio automatically(!)
        # this can bring some nice surprises :)
        for ep in endpoints:
            s.make_screenshot_chrome_headless(ep)
