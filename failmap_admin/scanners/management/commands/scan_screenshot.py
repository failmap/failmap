from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_screenshot import ScannerScreenshot


# todo: when tls scanner ends, it hangs.
# Only the latest ratings...
class Command(BaseCommand):
    help = 'Create a screenshot'

    def handle(self, *args, **options):
        s = ScannerScreenshot()

        eps = Endpoint.objects.all().filter(is_dead=False, url__not_resolvable=False)

        # Chrome headless, albeit single threaded, is pretty reliable and fast for existing
        # domains. This code is also the most updated. Waiting for firefox with screenshot
        # support. (they use --screenshot=<path>, so that might work multithreaded)
        # when only visiting existing domains (no timeouts) you'll have about 21 screenshots
        # per minute. Which is pretty ok.
        # todo: have a timeout of max N seconds per screenshot. Chrome doesn't have that.
        # killing python process might result in a random chrome process staying alive.
        for ep in eps:
            s.make_screenshot_chrome_headless(ep, True)
