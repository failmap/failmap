import logging
from datetime import datetime

import pytz
from typing import List

import failmap_admin.scanners.scanner_http as scanner_http
import failmap_admin.scanners.scanner_plain_http as scanner_plain_http
from failmap_admin.organizations.models import Url
from failmap_admin.scanners.scanner_dns import (brute_known_subdomains, certificate_transparency, nsec_scan)
from failmap_admin.scanners.scanner_screenshot import screenshot_urls

from ..celery import app


logger = logging.getLogger(__package__)


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

    onboard_urls(never_onboarded)


@app.task
def onboard_urls(urls: List[Url]):
    for url in urls:

        if url.is_top_level():
            brute_known_subdomains(urls=[url])
            certificate_transparency(urls=[url])
            nsec_scan(urls=[url])
        scanner_http.discover_endpoints(urls=[url])
        scanner_plain_http.scan_urls(urls=[url])
        screenshot_urls(urls=[url])
        # todo: add qualys tasks.

        url.onboarded = True
        url.onboarded_on = datetime.now(pytz.utc)
        url.save()
