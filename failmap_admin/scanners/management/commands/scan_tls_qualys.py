from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys, TlsQualysScratchpad


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    do_scan = True
    do_rate = True

    def handle(self, *args, **options):
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
            urls = Command.scannable_organization_urls(organization)

            if self.do_scan:
                scanme = []
                for url in urls:
                    scanme.append(url.url)  # possible with a more pythonic way probably
                s = ScannerTlsQualys()
                s.scan(scanme)

            if self.do_rate:
                dr = DetermineRatings()
                for url in urls:
                    dr.rate_url(url=url)
                dr.rate_organization(organization=organization)

        print("Done, scanned all!")

    @staticmethod
    def scannable_organization_urls(organization):
        """

        :return: list of url objects
        """
        urls_to_scan = []
        # This scanner only scans urls with endpoints (because we inner join endpoint_is_dead)

        # This scanner refuses to scan any urls that had a DNS / Not resolved error last time
        # by looking at the scan logs. Looking at the scan logs is slow. Currently a single
        # not resolved error does not kill a domain. Perhaps that it should be killed then.
        # Today we're not trusting the DNS stuff that qualys does it seems.

        # is_dead=False, endpoint__is_dead=False

        urls = Url.objects.filter(organization=organization,
                                  is_dead=False,
                                  not_resolvable=False)
        for url in urls:
            try:
                # Refuse to scan urls that are not resolvable, make them not resolvable.
                lastscan = TlsQualysScratchpad.objects.all().filter(domain=url.url).latest(
                    field_name="when")
                if "Unable to resolve domain name" not in lastscan.data:
                    urls_to_scan.append(url)
                else:
                    url.make_unresolvable("Scratchpad stated unresolvable domain.",
                                          lastscan.when)
                    print("Skipping domain due to unable to resolve domain "
                          "name in scratchpad: %s" % url)
            except ObjectDoesNotExist:
                # Especially if a last scan didn't exist, it should be scanned.
                # There have been cases in the past where a failed scan was not saved.
                print("Matching query didn't exist! :) - Also scanning domain: %s" % url.url)
                urls_to_scan.append(url)
                pass

        return urls_to_scan

    @staticmethod
    def scannable_new_urls():
        # find urls that don't have an qualys scan and are resolvable on https/443
        urls = Url.objects.filter(is_dead=False,
                                  not_resolvable=False,
                                  endpoint__port=443).exclude(endpoint__tlsqualysscan__isnull=True)

        print("These are the new urls:")
        for url in urls:
            print(url)

        raise NotImplemented
