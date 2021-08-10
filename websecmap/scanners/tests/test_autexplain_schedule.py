from datetime import datetime

from websecmap.organizations.models import Url
from websecmap.scanners.models import PlannedScan, State
from websecmap.scanners.scanner.autoexplain_trust_microsoft import plan_scan, compose_planned_scan_task
from websecmap.scanners.tests.test_plannedscan import (
    link_url_to_organization,
    create_url,
    create_organization,
    create_endpoint,
    create_endpoint_scan,
)

import logging

log = logging.getLogger(__package__)


def test_compose_scan_task(db, mocker):
    # disable the actual scan, so it can be run in a test:
    mocker.patch("websecmap.scanners.scanner.autoexplain_trust_microsoft", return_value=True)

    o = create_organization("Test")
    u1 = create_url("sip.example.com")
    link_url_to_organization(u1, o)
    e1 = create_endpoint(u1, 4, "https", 443)
    e2 = create_endpoint(u1, 6, "https", 443)
    create_endpoint_scan(e1, "tls_qualys_certificate_trusted", "not trusted", datetime(2020, 1, 1))
    create_endpoint_scan(e2, "tls_qualys_certificate_trusted", "not trusted", datetime(2020, 1, 1))

    u2 = create_url("sip.example2.com")
    link_url_to_organization(u2, o)
    e3 = create_endpoint(u2, 4, "https", 443)
    create_endpoint(u2, 6, "https", 443)
    create_endpoint_scan(e3, "tls_qualys_certificate_trusted", "not trusted", datetime(2020, 1, 1))

    # Planning a scan should be creating two scan tasks: for u1 and u2
    plan_scan()
    assert PlannedScan.objects.all().filter(state=State.requested.value).count() == 2

    # pick up the tasks:
    tasks = compose_planned_scan_task()
    assert PlannedScan.objects.all().filter(state=State.requested.value).count() == 0
    assert PlannedScan.objects.all().filter(state=State.picked_up.value).count() == 2

    # perform the task
    tasks.apply()

    # the planned scans should be finished now
    assert PlannedScan.objects.all().filter(state=State.finished.value).count() == 2
    assert PlannedScan.objects.all().filter(state=State.requested.value).count() == 0
    assert PlannedScan.objects.all().filter(state=State.picked_up.value).count() == 0


def debug_db_state():
    things = [Url, PlannedScan]

    for thing in things:
        for records in thing.objects.all():
            log.debug(records.__dict__)
