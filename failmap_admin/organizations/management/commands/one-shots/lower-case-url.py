import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.scanners.models import Endpoint, EndpointGenericScan, TlsQualysScan, Url

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    # todo: url on save, change to lower
    help = 'Get some ideas about relationships with uppercase characters (they should be lower case)'

    def handle(self, *args, **options):
        urls = Url.objects.all().filter(url__regex="[A-Z]")
        for url in urls:
            print(url)

            try:
                lowercase_urls = Url.objects.all().filter(url=url.url.lower())
                if lowercase_urls:
                    print("Has lower case variant %s, deleting uppercase." % lowercase_urls)

                endpoints = Endpoint.objects.all().filter(url=url)
                for endpoint in endpoints:
                    EndpointGenericScan.objects.all().filter(endpoint=endpoint).delete()
                    TlsQualysScan.objects.all().filter(endpoint=endpoint).delete()

                url.delete()  # doesn't this result in inconsistent relations?
            except ObjectDoesNotExist:
                print("Has NO lower case variant, updating to lowercase.")
                url.url = url.url.lower()
                url.save()
