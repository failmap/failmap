import datetime
import logging
from typing import List

import iso3166
import requests
from django.core.management.base import BaseCommand

from failmap.scanners.models import ScanProxy
from failmap.scanners.scanner.tls_qualys import check_proxy

log = logging.getLogger(__name__)


def valid_country_code(code):

    # let's hope openproxy.space does use iso3166 :)
    if code not in iso3166.countries_by_alpha2:
        raise ValueError("Countrycode not present in iso3166: %s" % code)

    return code


class Command(BaseCommand):
    """Imports proxies from openproxy.space"""

    def add_arguments(self, parser):
        parser.add_argument('countries', nargs='*', help='The scanner you want to use.', type=valid_country_code)
        super().add_arguments(parser)

    def handle(self, *args, **options):
        import_proxies_by_country(options['countries'])


def import_proxies_by_country(countries: List):
    """
    Proxies are retrieved per 50. We only want https proxies at the moment.

    :param countries:
    :return:
    """

    if not countries:
        countries = ["NL", "DE", "BE", "SE", "FR"]

    log.debug("Going to import proxies from %s" % countries)

    # ours:   1547644379
    # ours2:  1547645865107.048
    # theirs: 1547643411986
    # have to add some extra values it seems...
    timestamp = round(datetime.datetime.now().timestamp() * 1000)

    proxies = []
    for country in countries:
        for skip in range(0, 1000, 50):
            log.debug("Getting proxies for %s %s %s" % (country, skip, timestamp))
            try:
                response = requests.get(
                    "https://api.openproxy.space/short/country/%s?limit=50&skip=%s&ts=%s" % (country, skip, timestamp))

                result = response.json()
            except BaseException:
                break

            # error, nothing left
            if "status" in result:
                log.debug("Status returned: %s" % result['status'])
                break

            # more proxies.
            proxies += result
            log.debug("Currently having %s proxies listed." % len(proxies))

    # filtering out proxies per protocol. We don't need socks, http etc... only https.
    proxies_with_https = [proxy for proxy in proxies if "https" in proxy['protocols']]

    log.debug("There are %s proxies in this list that support https." % len(proxies_with_https))

    # add the new proxies.
    for proxy in proxies_with_https:

        address = "%s:%s" % (proxy['ip'], proxy['port'])

        if ScanProxy.objects.all().filter(address=address).exists():
            log.debug("Proxy with address %s already exists, skipping." % address)
            continue

        new_proxy = ScanProxy()
        new_proxy.protocol = "https"
        new_proxy.address = address
        new_proxy.save()
        log.debug("Added proxy with address %s" % address)

        # also kick off a test for the proxy to see if it still functions
        check_proxy.apply_async([new_proxy])
