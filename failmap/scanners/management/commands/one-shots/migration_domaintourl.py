import tldextract
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap.organizations.models import Organization
from failmap.scanners.models import Endpoint, TlsQualysScan, Url


class Command(BaseCommand):
    help = 'Further helps with obsoleting the endpoint.domain field, to endpoint.url.'

    """
    It should only be needed to run this script once when upgrading from very early versions
    of faalkaart. You probably don't need to run this anymore...
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        endpoints = Endpoint.objects.all().filter()
        missing_domains = []

        for endpoint in endpoints:
            if not endpoint.url:
                print("endpoint %s has no url, but has the domain %s" %
                      (endpoint.id, endpoint.domain))

                # let's see if there is a domain that is exactly matching the domain
                urls = Url.objects.all().filter(url__exact=endpoint.domain)
                # todo: organizaiton + url are unique... we're making an assumption here.
                saved = False
                for url in urls:
                    if url.url == endpoint.domain:
                        print("This domain has an equivalent url, saving...")
                        endpoint.url = url
                        endpoint.save()
                        saved = True

                # if there is no URL... then i guess we'll have to create it some way.
                # otherwise data will be lost, and we can't have that.
                # one thing that stands out is that all of these domains are dead.
                # since we filtered on is_dead at the endpoint query (line 17) we missed these
                # However: we DO have a scan date. And we DO have a date when they died.
                # So we can add the URL with a creation and dead day....
                # with testing these urls, some also appear to be alive. So wtf!
                # We can add the URL and then run a scan on them...
                # This is probably a migration error from the past.

                # first, make a list, to filter out the duplicates
                if not saved:
                    if endpoint.domain not in missing_domains:
                        missing_domains.append(endpoint.domain)

        # a lot of these domains can be automatically added using the methods of the admi interface.
        # We will add these domains as being dead, as is in the database. But will separately scan
        # all these domains to see if they are really dead. If not: more domains for us.
        # it's been verified some are very much alive.
        print("There are %s domains that don't have a URL. I mean... " % len(missing_domains))

        # let's try and find the right organization for them, and then add the domain, as dead
        # with the characteristics it has.
        for missing_domain in missing_domains:
            print("Attempting to place missing domain %s " % missing_domain)
            self.place_domain(missing_domain)

    def place_domain(self, missing_domain):
        extract = tldextract.extract(missing_domain)
        domainandtld = extract.domain + '.' + extract.suffix

        try:
            organization = Organization.objects.all().filter(url__url=domainandtld).first()
            print("%s belongs to %s" % (missing_domain, organization))

            if organization:
                first_scan = TlsQualysScan.objects.all().filter(
                    endpoint__domain=missing_domain).earliest("rating_determined_on")
                last_scan = TlsQualysScan.objects.all().filter(
                    endpoint__domain=missing_domain).latest("rating_determined_on")

                url = Url()
                url.created_on = first_scan.rating_determined_on
                url.is_dead = True
                url.is_dead_reason = "Found dead endpoint, but missing URL. Added dead url."
                url.is_dead_since = last_scan.rating_determined_on  # this is incorrect...
                url.organization = organization
                url.url = missing_domain
                url.save()
            else:
                print("No organization found for this url, try something else %s"
                      % missing_domain)

        except ObjectDoesNotExist:
            print("Some weird error")

        # The rest is all specialized work and needs to be added by hand.
        # We're going to do that to the dataset we're now testing on.
        # So let's make a nice backup and then make this the leading test data.
