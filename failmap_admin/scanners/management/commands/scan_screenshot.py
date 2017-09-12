from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_screenshot import ScannerScreenshot
from failmap_admin.organizations.models import Url

# Only the latest ratings...
class Command(BaseCommand):
    help = 'Create a screenshot'

    def handle(self, *args, **options):
        s = ScannerScreenshot()

        us = Url.objects.all().filter(endpoint__is_dead=False,
                                      endpoint__tlsqualysscan__qualys_rating__in=["F","C", "B", "A"])

        urllist = []
        for u in us:
            urllist.append("https://" + u.url)
            # urllist.append("http://" + u.url)
        # s.make_screenshot_threaded(urllist)  # doesn't work well with cd.
        # Affects all threads (and the main thread) since they all belong to the same process.
        # chrome headless has no option to start with a working directory...
        # working with processes also results into the same sorts of troubles.
        # maybe chrome shares some state for the cwd in their processes?

        # endpoint without TLS, is dead? endpoint exists, but no tls. Should we make a :80 endpoint
        # then?
        for u in urllist:
            # s.make_screenshot_phantomjs(u)
            s.make_screenshot_chrome_headless(u)


        # for u in us:
            # Urls are stored without protocols.
          #  s.make_screenshot("https://" + u.url)
           # s.make_screenshot("http://" + u.url)

        # s.make_screenshot("http://faalkaart.nl")
        # s.make_screenshot("https://tweakers.net")
        # s.make_screenshot("http://tweakers.net")
