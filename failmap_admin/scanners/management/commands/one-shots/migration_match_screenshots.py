from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Screenshot


class Command(BaseCommand):
    help = 'Connects screenshots to Urls based on the domain field. In case of bugs.'

    def handle(self, *args, **options):
        # reconstruct the existance of urls, filling created_on with the first discovered_on ep.

        screenshots = Screenshot.objects.all()
        for screenshot in screenshots:
            if not screenshot.url:
                try:
                    # remove the protocol.
                    url = screenshot.domain.replace("https://", "")
                    url = url.replace("http://", "")

                    # and remove the port if there is one
                    try:
                        if url.index(':'):
                            url = url[0:url.index(':')]
                    except ValueError:
                        # not in string. fine.
                        pass

                    screenshot.url = Url.objects.all().filter(url=url).first()
                except ObjectDoesNotExist:
                    print("No URL exists for screenshot: %s, saving without one." % screenshot)

                screenshot.save()
