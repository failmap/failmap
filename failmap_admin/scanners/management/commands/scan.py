from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys, TlsQualysScratchpad


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    def handle(self, *args, **options):
        while 1:
            self.scan()

    def scan(self):
        # todo: figure out a way to "resume" from the last scanned organization,
        # Not something that influenced from random scans from the admin interface.
        o = Organization.objects.all()
        for organization in o:
            urls_to_scan = []
            # This scanner only scans urls with endpoints (because we inner join endpoint_is_dead)
            # There should also be a routine that only scans urls that don't have an endpoint yet??

            # This scanner refuses to scan any urls that had a DNS / Not resolved error last time
            # by looking at the scan logs. Looking at the scan logs is slow. Currently a single
            # not resolved error does not kill a domain. Perhaps that it should be killed then.
            # Today we're not trusting the DNS stuff that qualys does it seems.

            # is_dead=False, endpoint__is_dead=False
            urls = Url.objects.filter(organization=organization, is_dead=False)
            for url in urls:
                try:
                    # Check in the scratchpad if a DNS error was given
                    lastscan = TlsQualysScratchpad.objects.all().filter(domain=url.url).latest(
                        field_name="when")
                    if "Unable to resolve domain name" not in lastscan.data:
                        urls_to_scan.append(url.url)
                    else:
                        print("Skipping domain due to unable to resolve domain name in scratchpad.")
                except ObjectDoesNotExist:
                    # Especially if a last scan didn't exist, it should be scanned.
                    # There have been cases in the past where a failed scan was not saved.
                    print("Matching query didn't exist! :) - Also scanning domain: %s" % url.url)
                    urls_to_scan.append(url.url)
                    pass

            # scan per organization, to lower the amount of time for updates on the map
            s = ScannerTlsQualys()
            s.scan(urls_to_scan)

            # after the scan finished, update the ratings for the urls and then the organization.
            dr = DetermineRatings()
            for url in urls:
                dr.rate_url(url=url)

            dr.rate_organization(organization=organization)

        print("Done, scanned all!")
