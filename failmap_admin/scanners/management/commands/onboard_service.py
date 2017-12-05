import logging
from time import sleep

from django.core.management.base import BaseCommand

from failmap_admin.scanners.onboard import onboard_new_urls

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Automatically performs initial scans and tests on new urls.'

    def handle(self, *args, **options):
        runservice()


def runservice():
    try:
        logger.info("Started onboarding.")
        while True:
            onboard_new_urls()
            logger.info("Waiting for urls to be onboarded. Sleeping for 60 seconds.")
            sleep(60)
    except KeyboardInterrupt:
        logger.info("Onboarding interrupted.")
        do_continue = input("Do you wish to quit? Y/n")
        if "n" in do_continue or "N" in do_continue:
            runservice()
        else:
            logger.info("Stopped onboarding.")
