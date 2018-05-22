
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap.organizations.models import Url
from failmap.scanners.models import Endpoint

# This script estimates when an URL started to exist, and when endpoints started to exist.
# This is created when discovered the Endpoint data was not complete enough: missing "when"
# the endpoint was created. Without it, it could not be easily determined what endpoints where
# alive at what moment to give accurate history.


class Command(BaseCommand):
    help = 'Create some discovery dates for endpoints. Only run this once after migration.'

    def handle(self, *args, **options):
        # reconstruct the existance of urls, filling created_on with the first discovered_on ep.

        urls = Url.objects.all()
        for url in urls:

            try:
                e = Endpoint.objects.all().filter(url=url).first()
                url.created_on = e.discovered_on
                url.save()
                print("Url %s was discovered on %s" % (url, url.created_on))
            except ObjectDoesNotExist:
                print("There was no endpoint ever for this url...")
            except Exception:
                print("%s has something strange, probably no endpoints." % url)
