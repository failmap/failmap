import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import (rate_organization_efficient, rate_organizations,
                                                rate_url, rerate_url_with_timeline)
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys, TlsQualysScratchpad
from failmap_admin.scanners.state_manager import StateManager

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    def add_arguments(self, parser):
        parser.add_argument(
            '--manual', '-o',
            help="Give an url to scan via command line.",
            nargs=1,
            required=False,
            default=False,
            type=bool
        )

    do_scan = True
    do_rate = True

    def handle(self, *args, **options):
        if options['manual']:
            url = input("Type the url, without protocol:")
            url = Url.objects.all().filter(url=url).first()

            s = ScannerTlsQualys()
            s.scan([url.url])

            rerate_url_with_timeline(url=url)
            rate_organization_efficient(organization=url.organization)
        else:
            while 1:
                self.scan()

    def scan(self):
        # todo: sort the organizations on the oldest scanned first, or never scanned first.
        # or make a separate part that first scans all never scanned stuff, per organization
        # so new stuff has some priority.

        # Not something that influenced from random scans from the admin interface.
        # scan per organization, to lower the amount of time for updates on the map
        # after the scan finished, update the ratings for the urls and then the organization.

        # https://stackoverflow.com/questions/13694034/is-a-python-list-guaranteed-to-have-its-
        # elements-stay-in-the-order-they-are-inse
        resume = StateManager.create_resumed_organizationlist(scanner="ScannerTlsQualys")

        for organization in resume:
            StateManager.set_state("ScannerTlsQualys", organization.name)
            Command.scan_new_urls()  # always try to scan new urls first, regardless of org.
            Command.scan_organization(organization)

    @staticmethod
    def scan_organization(organization):
        """

        :return: list of url objects
        """
        # This scanner only scans urls with endpoints (because we inner join endpoint_is_dead)

        # Using the HTTP scanner, it's very easy and quick to see if a url resolves.
        # This is much faster than waiting 1.5 minutes for qualys to figure it out.
        # So we're only scanning what we know works.
        logger.info("Scanning organization: %s" % organization)

        urls = Url.objects.filter(organization=organization,
                                  is_dead=False,
                                  not_resolvable=False,
                                  endpoint__is_dead=False,
                                  endpoint__protocol="https",
                                  endpoint__port=443)

        if not urls:
            logger.info("There are no alive https urls for this organization: %s" % organization)
            return

        s = ScannerTlsQualys()
        s.scan([url.url for url in urls])

        for url in urls:
            rerate_url_with_timeline(url=url)
        rate_organization_efficient(organization=organization)

    @staticmethod
    def scan_new_urls():
        # find urls that don't have an qualys scan and are resolvable on https/443
        # todo: perhaps find per organization, so there will be less ratings? (rebuilratings cleans)
        urls = Url.objects.filter(is_dead=False,
                                  not_resolvable=False,
                                  endpoint__port=443,
                                  ).exclude(endpoint__tlsqualysscan__isnull=False)

        if urls.count() < 1:
            logger.info("There are no new urls.")
            return

        logger.info("Good news! There are %s urls to scan!" % urls.count())
        pie = """
                                            (
                       (
               )                    )             (
                       )           (o)    )
               (      (o)    )     ,|,            )
              (o)     ,|,          |~\    (      (o)
              ,|,     |~\    (     \ |   (o)     ,|,
              \~|     \ |   (o)    |`\   ,|,     |~\\
              |`\     |`\@@@,|,@@@@\ |@@@\~|     \ |
              \ | o@@@\ |@@@\~|@@@@|`\@@@|`\@@@o |`\\
             o|`\@@@@@|`\@@@|`\@@@@\ |@@@\ |@@@@@\ |o
           o@@\ |@@@@@\ |@@@\ |@@@@@@@@@@|`\@@@@@|`\@@o
          @@@@|`\@@@@@@@@@@@|`\@@@@@@@@@@\ |@@@@@\ |@@@@
          p@@@@@@@@@@@@@@@@@\ |@@@@@@@@@@|`\@@@@@@@@@@@q
          @@o@@@@@@@@@@@@@@@|`\@@@@@@@@@@@@@@@@@@@@@@o@@
          @:@@@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@o@@::@
          ::@@::@@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@o@@:@@::@
          ::@@::@@@@::oo@@@@oo@@@@@ooo@@@@@o:::@@@::::::
          %::::::@::::::@@@@:::@@@:::::@@@@:::::@@:::::%
          %%::::::::::::@@::::::@:::::::@@::::::::::::%%
          ::%%%::::::::::@::::::::::::::@::::::::::%%%::
        .#::%::%%%%%%:::::::::::::::::::::::::%%%%%::%::#.
      .###::::::%%:::%:%%%%%%%%%%%%%%%%%%%%%:%:::%%:::::###.
    .#####::::::%:::::%%::::::%%%%:::::%%::::%::::::::::#####.
   .######`:::::::::::%:::::::%:::::::::%::::%:::::::::'######.
   .#########``::::::::::::::::::::::::::::::::::::''#########.
   `.#############```::::::::::::::::::::::::'''#############.'
    `.######################################################.'
      ` .###########,._.,,,. #######<_\##################. '
         ` .#######,;:      `,/____,__`\_____,_________,_____
            `  .###;;;`.   _,;>-,------,,--------,----------'
                `  `,;' ~~~ ,'\######_/'#######  .  '
                    ''~`''''    -  .'/;  -    '       -Catalyst
        """
        logger.info(pie)

        logger.debug("These are the new urls:")
        for url in urls:
            logger.debug(url)

        s = ScannerTlsQualys()

        import math

        # Scan the new urls per 30, which takes about 30 minutes.
        # Why: so scans will still be multi threaded and the map updates frequently
        #      and we have a little less ratings if multiple urls are from one organization
        batch_size = 30
        logger.debug("Scanning new urls in batches of: %s" % batch_size)
        i = 0
        iterations = int(math.ceil(len(urls) / batch_size))
        while i < iterations:
            logger.info("New batch %s: from %s to %s" % (i, i * batch_size, (i + 1) * batch_size))
            myurls = urls[i * batch_size:(i + 1) * batch_size]
            i = i + 1

            # ah yes, give "real" urls.. .not url objects.
            urlstrings = []
            for url in myurls:
                urlstrings.append(url.url)
            s.scan(urlstrings)

            for url in myurls:
                rerate_url_with_timeline(url=url)

            for url in myurls:
                rate_organization_efficient(organization=url.organization)

        return urls
