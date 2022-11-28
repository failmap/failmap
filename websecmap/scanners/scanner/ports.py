"""
Marks all ports that are in PORTSCAN_SHOULD_BE_INTERNAL_PORTS as being "not needed for external exposure".

Given there is only rarely a need for hosting something for the public. All the other stuff should be on the VPN.

Note that the definition of acceptable ports changes often.

An example: 8080 is not a port where something should be hosted. Just because what is hosted on those ports is usually
a management application.

This script does not do portscanning, see bannergrab_nmap for that. It just marks ports as 'should not be open'.
"""

from typing import List

from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanmanager import store_endpoint_scan_result
import logging


from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.scanners.scanner.__init__ import (
    allowed_to_scan,
)


SCANNER_NAME = "ports"

PORTS_SHOULD_NOT_BE_OPEN = "port_should_not_be_open"
PORTS_IS_CLOSED = "port_could_not_be_found_anymore"


log = logging.getLogger(__name__)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def mark_unusual_ports():
    if not allowed_to_scan(SCANNER_NAME):
        log.warning("Scanner %s is requested but not enabled.", SCANNER_NAME)
        return

    mark_unusual()
    clear_the_rest()


def string_to_list_of_ints(data: str) -> List[int]:
    new = []
    try:
        new.extend(int(item) for item in data.split(","))
    except ValueError:
        log.error("PORTSCAN_SHOULD_BE_INTERNAL_PORTS is not a valid list of ips. Example: '80,443,400'")
        return []

    return new


def get_configured_ports() -> List[int]:
    ports = string_to_list_of_ints(constance_cached_value("PORTSCAN_SHOULD_BE_INTERNAL_PORTS"))
    log.debug("Configured ports that should not be open: %s", ports)
    return ports


def mark_unusual():
    endpoints_with_weird_ports = Endpoint.objects.all().filter(port__in=get_configured_ports(), is_dead=False)

    for endpoint in endpoints_with_weird_ports:
        store_endpoint_scan_result(
            scan_type=SCANNER_NAME, endpoint_id=endpoint.id, rating=PORTS_SHOULD_NOT_BE_OPEN, message=""
        )


def clear_the_rest():
    epgss = (
        EndpointGenericScan.objects.all()
        .filter(
            rating=PORTS_SHOULD_NOT_BE_OPEN,
            is_the_latest_scan=True,
        )
        .exclude(
            endpoint__port__in=get_configured_ports(),
        )
    )
    for epgs in epgss:
        store_endpoint_scan_result(
            scan_type=SCANNER_NAME, endpoint_id=epgs.endpoint.id, rating=PORTS_IS_CLOSED, message=""
        )
