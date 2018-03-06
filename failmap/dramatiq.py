import logging
import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from dramatiq.results.backends import RedisBackend, StubBackend

log = logging.getLogger(__name__)


def setbroker(watcher=False):
    broker_url = os.environ.get('BROKER', 'redis://localhost:6379/0')

    if broker_url.startswith('redis'):
        broker = RedisBroker(url=broker_url)
        broker.add_middleware(dramatiq.results.Results(backend=RedisBackend(client=broker.client)))
    else:
        broker = StubBroker()
        broker.add_middleware(dramatiq.results.Results(backend=StubBackend()))

    broker.add_middleware(dramatiq.middleware.AgeLimit())
    broker.add_middleware(dramatiq.middleware.Callbacks())
    broker.add_middleware(dramatiq.middleware.Retries())
    broker.add_middleware(dramatiq.middleware.Pipelines())

    dramatiq.set_broker(broker)
    dramatiq.set_encoder(dramatiq.PickleEncoder)


setbroker()


@dramatiq.actor(store_results=True)
def ping():
    return 'pong'
