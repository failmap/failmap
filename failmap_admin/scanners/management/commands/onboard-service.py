import logging
from datetime import datetime
from time import sleep

import pytz
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.scanner_dns import brute_known_subdomains, certificate_transparency_scan
from failmap_admin.scanners.scanner_http import scan_urls_on_standard_ports
from failmap_admin.scanners.scanner_plain_http import scan_url
from failmap_admin.scanners.scanner_screenshot import screenshot_urls

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Automatically performs initial scans and tests on new urls.'

    def handle(self, *args, **options):
        try:
            logger.info("Started onboarding.")
            while True:
                onboard()
                logger.info("Waiting for more urls to be onboarded. Sleeping for 60 seconds.")
                sleep(60)
        except KeyboardInterrupt:
            logger.info("Onboarding interrupted.")
            do_continue = input("Do you wish to quit? Y/n")
            if "n" in do_continue or "N" in do_continue:
                self.handle()
            else:
                logger.info("Stopped onboarding.")


# todo: make scan log, so you can see what has been scanned, and what completed.
def onboard():

    urls = onboard_gather()
    for url in urls:
        # scan for http/https endpoints
        if url.is_top_level():
            # some DNS scans, to find more urls to onboard.
            brute_known_subdomains([url])
            certificate_transparency_scan([url])
        scan_urls_on_standard_ports([url])
        scan_url(url)
        screenshot_urls([url])
        # tls scans are picked up by scanner_tls_qualys and may take a while.
        # other scans the same. They will do the ratings.

        url.onboarded = True
        url.onboarded_on = datetime.now(pytz.utc)
        url.save()


def onboard_existing_urls():
    """A quick fix for an existing database."""
    urls = Url.objects.all()
    for url in urls:
        url.onboarded = True
        url.onboarded_on = datetime.now(pytz.utc)
        url.save()


def onboard_gather():

    never_onboarded = Url.objects.all().filter(onboarded=False)

    if never_onboarded.count() > 0:
        cyber = """

................................................................................
.......-:////:.....:-.......::...-///////:-......://////////:..../////////:.....
...../mMMMMMMMN...NMM+.....hMMy..+MMMMMMMMMNy-...dMMMMMMMMMMMN..-MMMMMMMMMMNy...
....+MMMhsssss/...MMMd-.../NMMd..+MMMyssssmMMN-..dMMNssssssss/..-MMMdsssssNMMy..
...+MMMy........../mMMNo-yMMMh-..+MMM:....:MMM+..dMMm...........-MMMy+++++NMMh..
../MMMy.............sMMMMMMm/....+MMMo+++odMMM:..dMMm+++/.......-MMMMMMMMMMMd-..
..hMMN...............:dMMMy......+MMMMMMMMMMMo...dMMMMMMM/......-MMMhhMMMd+-....
../MMMy...............oMMM-......+MMMo++++dMMM:..dMMm+++/.......-MMMo.sMMMs.....
...+MMMy..............oMMM-......+MMM:....:MMM+..dMMm...........-MMMo..+MMMh....
....+MMMdsssss/.......oMMM-......+MMMysssymMMN-..dMMNssssssss/..-MMMo.../NMMm-..
...../dMMMMMMMN......./MMN.......+MMMMMMMMMNy-...dMMMMMMMMMMMN...NMM+....-mMMs..
.......-::::::.........-:........-::::::::-......::::::::::::.....:-.......::...
................................................................................
        """
        logger.info("There are %s new urls to onboard! %s" % (never_onboarded.count(), cyber))

    return never_onboarded
