from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_screenshot import ScannerScreenshot


# todo: when tls scanner ends, it hangs.
# Only the latest ratings...
class Command(BaseCommand):
    help = 'Create a screenshot'

    https_screenshot = False
    http_screenshot = True

    def handle(self, *args, **options):
        s = ScannerScreenshot()

        urllist = []
        if self.https_screenshot:
            us = Url.objects.all().filter(
                not_resolvable=False,
                endpoint__is_dead=False,
                endpoint__protocol="https",
                endpoint__tlsqualysscan__qualys_rating__in=["F", "C", "B", "A",
                                                            "C", "A+", "A-", "M", "D"])

            for u in us:
                domain = ("https://%s:%s" % (u.url, 443))
                urllist.append(domain)

        if self.http_screenshot:
            eps = Endpoint.objects.all().filter(is_dead=False,
                                                protocol="http",
                                                url__not_resolvable=False)

            # To make screenshots of the ipv6 addresses, we must only DNS resolve IPv6.
            # We probably cannot force that in python. Due to SNI, it's no use to surf to
            # an IPv6 address directly (although we could, for another test)
            for ep in eps:
                domain = ("http://%s:%s" % (ep.url.url, ep.port))
                urllist.append(domain)

        for u in urllist:
            # Chrome headless, albeit single threaded, is pretty reliable and fast for existing
            # domains. This code is also the most updated. Waiting for firefox with screenshot
            # support. (they use --screenshot=<path>, so that might work multithreaded)
            s.make_screenshot_chrome_headless(u)
