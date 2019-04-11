import datetime
from typing import List

import requests

from websecmap.celery import app
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner.tls_qualys import check_proxy
from websecmap.scanners.tasks import log


@app.task(queue='storage')
def import_proxies_by_country(countries: List = [], amount=100, **kwargs):
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
        for skip in range(0, amount, 50):
            log.debug("Getting proxies for %s %s %s" % (country, skip, timestamp))

            response = requests.get(
                "https://api.openproxy.space/country/%s?limit=50&skip=%s&ts=%s" % (country, skip, timestamp))

            result = response.json()

            # error, nothing left
            if "status" in result:
                log.debug("Status returned: %s" % result['status'])
                break

            # more proxies.
            proxies += result
            log.debug("Currently having %s proxies listed." % len(proxies))

    # filtering out proxies per protocol. We don't need socks, http etc... only https.
    # the new API has numbers for protocols.
    # 1 = HTTP
    # 2 = HTTPS
    # 3 = SOCKS4
    # 4 = not relevant...
    proxies_with_https = [proxy for proxy in proxies if 2 in proxy['protocols']]

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


@app.task(queue='storage')
def check_existing_alive_proxies():

    proxies = ScanProxy.objects.all().filter(
        is_dead=False,
        manually_disabled=False,
    )

    for proxy in proxies:
        check_proxy.apply_async([proxy])
