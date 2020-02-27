import asyncio
import logging
from typing import List

from proxybroker import Broker

from websecmap.celery import app
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner.tls_qualys import check_proxy

log = logging.getLogger(__name__)


async def save(proxies):
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


@app.task(queue='storage')
def find(countries: List = None, amount: int = 5, timeout: float = 0.5, **kwargs):
    # Warning: this will only work with celery 5. This is not released yet.

    if not countries:
        countries = ['US', 'DE', 'SE', 'FR', 'NL', 'GB', 'ES', 'DK', 'NO', 'FI']

    proxies = asyncio.Queue()
    broker = Broker(proxies)
    tasks = asyncio.gather(broker.find(types=['HTTPS'],
                                       limit=amount,
                                       countries=countries,
                                       timeout=timeout,
                                       ),
                           save(proxies))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tasks)


@app.task(queue='storage')
def check_existing_alive_proxies():

    proxies = ScanProxy.objects.all().filter(
        is_dead=False,
        manually_disabled=False,
    )

    for proxy in proxies:
        check_proxy.apply_async([proxy])
