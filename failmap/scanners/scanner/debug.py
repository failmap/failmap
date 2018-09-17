import logging

from celery import Task, group
from constance import config

from failmap.celery import app
from failmap.scanners.models import Endpoint
from failmap.scanners.scanner.scanner import endpoint_filters, q_configurations_to_scan

log = logging.getLogger(__name__)


@app.task(queue='storage')
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """
    Helps with identifying issues with scanners. It shows the relevant permissions, configurations and lists the
    organizations, urls and endpoints in a convenient way. This can only run in direct mode and will not result in
    tasks.
    All messages are returned as log messages.

    :param organizations_filter:
    :param urls_filter:
    :param endpoints_filter:
    :return:
    """
    log.info("Debug info for scanners:")

    # done: list allowed_to_scan
    vars = dir(config)
    log.info("")
    log.info("Scan permissions:")
    log.info("Can be adjusted in the admin interface at Configuration")
    for var in vars:
        if var[0:5] == "SCAN_":
            log.info("%-30s: %-5s" % (var, getattr(config, var)))

    # done: list q_configurations_to_scan on all levels.
    log.info("")
    log.info("Scan configurations (regions set allowed to be scanned)")
    log.info("Can be adjusted in the admin interface at __MAP__ Configuration")
    log.info("Empty means nothing will be scanned (basically exceptions)")
    log.info("Organizations: %s" % q_configurations_to_scan(level='organization'))
    log.info("Urls: %s" % q_configurations_to_scan(level='url'))
    log.info("Endpoints: %s" % q_configurations_to_scan(level='endpoint'))

    # todo: show list of selected urls, endpoints and organizations.
    log.info("")
    log.info("Endpoints that are selected based on parameters:")
    log.info("Other filters may apply depending on selected scanner. For example: scan ftp only selects ftp endpoints")
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    for endpoint in endpoints:
        log.info("%-3s %-20s %-30s: IPv%-1s %s/%s" % (endpoint.url.organization.first().country,
                                                      endpoint.url.organization.first().name,
                                                      endpoint.url.url,
                                                      endpoint.ip_version, endpoint.protocol, endpoint.port))

    log.info("")
    log.info("End of scan debug")
    log.info("")
    # return nothing.
    return group()
