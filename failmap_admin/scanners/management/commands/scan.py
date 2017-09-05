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
        # since it can take a while to do the whole circle of organizations...
        # if we take the last scanned url to resume... could have consequences form
        # the admin interface, that's not good.
        o = Organization.objects.all()
        for organization in o:
            urls_to_scan = []
            # save time, don't scan the dead urls.
            # only urls are scanned that have endpoints... when are the urls scanned without endpoints?
            # and how do we know the urls without endpoints have been scanned (and for example got
            # an DNS error / not resolved domain etc?)... -> we can make some "initial scan" feature..
            # since we have scratches from every scan, we can see if something has happened ever before
            # on a url. (but we don't save a scan without endpoints... so we will not know in the scans table).

            # todo: comment cleanup
            # todo: adding is_dead to the filter again. Perhaps as a parameter.
            # is_dead=False, endpoint__is_dead=False
            urls = Url.objects.filter(organization=organization)
            for url in urls:
                # Check in the scratchpad if a DNS error was given
                # this is a bit of a hacky workaround. The scanner is independent of what we feed it.
                # it will just scan. So we should take care the correct stuff is given.
                try:
                    lastscan = TlsQualysScratchpad.objects.all().filter(domain=url.url).latest(
                        field_name="when")
                    if "Unable to resolve domain name" not in lastscan.data:
                        urls_to_scan.append(url.url)
                    else:
                        print("Skipping domain due to unable to resolve domain name in scratchpad.")
                except:
                    # of course it can be that the lastscan doesn't exist...
                    # in that case, we'll have to make sure that there will be a scan, so the error
                    # or anything else can be recorded.
                    # todo: exception specifieker maken
                    print("Matching query didn't exist! :) - Also scanning domain: %s" % url.url)
                    urls_to_scan.append(url.url)
                    pass

            # scan per organization, to lower the amount of time for updates
            s = ScannerTlsQualys()
            s.scan(urls_to_scan)

            # the scanner still ends sequentially, so... we can now update the ratings
            # for some reason (probably caching?) urls are rated separately from organization
            dr = DetermineRatings()
            for url in urls:
                dr.rate_url(url=url)

            dr.rate_organization(organization=organization)

        print("Done, scanned all!")
