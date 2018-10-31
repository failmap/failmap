import logging

import flower.utils.broker

from failmap.celery import app
from failmap.celery.worker import QUEUES_MATCHING_ROLES
from failmap.hypersh.models import ContainerGroup

log = logging.getLogger(__name__)


@app.task(queue="hyper")
def autoscale():
    """Calculates the number of needed scanners based on the number of tasks in the queue.

    Queues are defined in failmap.celery.worker
    Containergroups are defined in failmap.hypersh.models (and are managed in the admin interface)
    """

    if 'redis://' not in app.conf.broker_url:
        log.info("Autoscale only works on redis.")
        return

    perform_autoscale(containergroup_name="Qualys scanners", scan_queue="qualys")
    perform_autoscale(containergroup_name="V4 Scanner", scan_queue="ipv4")


def perform_autoscale(containergroup_name, scan_queue):
    try:
        cg = ContainerGroup.objects.all().get(name=containergroup_name)
    except ContainerGroup.DoesNotExist:
        # fine, the cg was not configured. Happens.
        log.error("Containergroup %s not found!" % containergroup_name)
        return

    # default is a monitor for all queues
    queues = [q.name for q in QUEUES_MATCHING_ROLES['default']]

    # @gen.coroutine sometimes misses an event loop. Therefore make one.
    # See failmap.celery.__init__ for more information.
    # 'solves': RuntimeError: There is no current event loop in thread 'Thread-3'.
    try:
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
    except BaseException:
        # an eventloop already exists.
        pass

    # use flower to not reinvent the wheel on querying queue statistics
    broker = flower.utils.broker.Broker(app.conf.broker_url, broker_options=app.conf.broker_transport_options)
    queue_stats = broker.queues(queues).result()

    for stat in queue_stats:

        if stat['name'] == scan_queue and stat['messages'] > 0:
            maximize(cg)
            return

        if stat['name'] == scan_queue and stat['messages'] == 0:
            minimize(cg)
            return

    log.error("Queue %s not found!" % scan_queue)


def maximize(cg):
    cg.desired = cg.maximum
    cg.save(update_fields=['desired'])
    log.info("%s scaling up to maximum." % cg.name)


def minimize(cg):
    cg.desired = cg.minimum
    cg.save(update_fields=['desired'])
    log.info("%s scaling up to minimum." % cg.name)
