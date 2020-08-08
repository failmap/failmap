"""
Below approaches DO NOT work with eventlet AND + OR celery scheduling. This should not be included in anything
that is autodiscovered with celery or tests. You have been warned.

"""
import asyncio
import logging
from typing import List

from proxybroker import Broker

from websecmap.scanners.models import ScanProxy

log = logging.getLogger(__name__)


def find_new_proxies(countries: List = None, amount: int = 5, timeout: float = 0.5, **kwargs):
    # Warning: this will only work with celery 5. This is not released yet.

    if not countries:
        countries = ['US', 'DE', 'SE', 'FR', 'NL', 'GB', 'ES', 'DK', 'NO', 'FI', 'BE', 'PT', 'AT', 'PL']

    proxies = asyncio.Queue()
    broker = Broker(proxies)
    tasks = asyncio.gather(broker.find(types=['HTTPS'],
                                       limit=amount,
                                       countries=countries,
                                       timeout=timeout,
                                       ),
                           save_new_proxy(proxies))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tasks)


async def save_new_proxy(proxies):
    """Save proxies to a file."""

    while True:
        proxy = await proxies.get()
        if proxy is None:
            break

        address = f"{proxy.host}:{proxy.port}"
        if not ScanProxy.objects.all().filter(address=address).exists():
            sp = ScanProxy()
            sp.address = f"{proxy.host}:{proxy.port}"
            sp.protocol = "https"
            sp.request_speed_in_ms = round(proxy.avg_resp_time * 1000)
            sp.save()
            log.debug(f"Added proxy: {sp}")
        else:
            log.debug(f"Proxy with address {address} already exists.")
