import logging

import flower.utils.broker

from failmap.celery import app
from failmap.celery.worker import WORKER_QUEUE_CONFIGURATION
from failmap.hypersh.models import ContainerGroup

log = logging.getLogger(__name__)


@app.task
def autoscale():
    """Calculates the number of needed scanners based on the number of tasks in the queue.

    It will currently only work for Qualys tasks to see how / if it works. The ContainerGroup that is
    autoscaled has to be named "Qualys scanners".

    While calculation is fast, scaling is pretty slow. Just run this once every hour and see if you can speed it up.
    """

    cg = ContainerGroup.objects.all().get(name="Qualys scanners")

    if 'redis://' in app.conf.broker_url:
        queue_names = [q.name for q in WORKER_QUEUE_CONFIGURATION['default']]

        # use flower to not reinvent the wheel on querying queue statistics
        broker = flower.utils.broker.Broker(app.conf.broker_url, broker_options=app.conf.broker_transport_options)
        queue_stats = broker.queues(queue_names).result()

        for stat in queue_stats:
            if stat['name'] == "scanners.qualys" and stat['messages'] > 0:
                cg.desired = cg.maximum
                cg.save(update_fields=['desired'])
                log.info("Qualys scanners are scaling up to maximum.")
            elif stat['name'] == "scanners.qualys" and stat['messages'] == 0:
                cg.desired = 0
                cg.save(update_fields=['desired'])
                log.info("Qualys scanners are scaling back to 0.")
