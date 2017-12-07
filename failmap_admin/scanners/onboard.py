import logging
from datetime import datetime
from typing import List

import pytz

import failmap_admin.scanners.scanner_http as scanner_http
import failmap_admin.scanners.scanner_plain_http as scanner_plain_http
from failmap_admin.organizations.models import Url
from failmap_admin.scanners.scanner_dns import (brute_known_subdomains, certificate_transparency,
                                                nsec)
from failmap_admin.scanners.scanner_screenshot import screenshot_urls

from ..celery import app

logger = logging.getLogger(__package__)


@app.task
def onboard_new_urls():
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
    else:
        logger.info("No new urls to onboard.")

    onboard_urls(never_onboarded)


@app.task
def onboard_urls(urls: List[Url]):
    for url in urls:
        logger.info("Onboarding %s" % url)

        if url.is_top_level():
            logger.debug("Brute known subdomains: %s" % url)
            brute_known_subdomains(urls=[url])

            logger.debug("Certificate transparency: %s" % url)
            certificate_transparency(urls=[url])

            logger.debug("nsec: %s" % url)
            nsec(urls=[url])

        # tasks
        logger.debug("Discover endpoints: %s" % url)
        scanner_http.discover_endpoints(urls=[url])

        # requires endpoints to be discovered, how to run groups of tasks sequentially?
        logger.debug("Plain_http: %s" % url)
        scanner_plain_http.scan_urls(urls=[url])

        # requires endpoints to be discovered
        logger.debug("Screenshots: %s" % url)
        screenshot_urls(urls=[url])

        # security headers and new urls are handled elsewhere.

        url.onboarded = True
        url.onboarded_on = datetime.now(pytz.utc)
        url.save()
