from django.core.management.base import BaseCommand

from failmap_admin.scanners.models import Url
from failmap_admin.scanners.models import Endpoint


class Command(BaseCommand):
    help = 'Further helps with obsoleting the endpoint.domain field, to endpoint.url.'

    """
    It should only be needed to run this script once when upgrading from very early versions
    of faalkaart. You probably don't need to run this anymore...
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        endpoints = Endpoint.objects.all().filter(is_dead=False)

        for endpoint in endpoints:
            if not endpoint.url:
                print("endpoint %s has no url, but has the domain %s" %
                      (endpoint.id, endpoint.domain))

                # let's see if there is a domain that is exactly matching the domain
                urls = Url.objects.all().filter(url__exact=endpoint.domain)
                for url in urls:
                    if url.url == endpoint.domain:
                        print("This domain has an equivalent url, saving...")
                        endpoint.url = url
                        endpoint.save()
