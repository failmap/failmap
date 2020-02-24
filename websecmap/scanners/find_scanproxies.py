import asyncio
import logging

from proxybroker import Broker

from websecmap.scanners.models import ScanProxy

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


def find():
    proxies = asyncio.Queue()
    broker = Broker(proxies)
    tasks = asyncio.gather(broker.find(types=['HTTPS'],
                                       limit=50,
                                       countries=['US', 'DE', 'SE', 'FR', 'NL', 'GB', 'ES', 'DK', 'NO', 'FI'],
                                       timeout=0.5,
                                       ),
                           save(proxies))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(tasks)
