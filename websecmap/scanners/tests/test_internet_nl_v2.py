import logging
from datetime import datetime, timedelta

from websecmap.scanners.models import InternetNLV2Scan, InternetNLV2StateLog
from websecmap.scanners.scanner.internet_nl_v2_websecmap import (initialize_scan,
                                                                 progress_running_scan,
                                                                 update_state)

log = logging.getLogger('websecmap')


def test_internet_nl_logging(db):

    # todo: make sure that never an empty list is added in normal situations?
    scan = initialize_scan("web", [])
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested"

    update_state(scan, "testing", "just a test")
    update_state(scan, "error", "an irrecoverable error occurred")

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "error"

    # requested plus two above states
    assert InternetNLV2StateLog.objects.all().count() == 3

    # a progressed scan will not do anything, as there is no recoverable state.
    progress_running_scan(scan)
    assert InternetNLV2StateLog.objects.all().count() == 3

    # a recoverable error will make sure the last known correct state is set, which is requested...
    update_state(scan, "configuration_error", "This is a recoverable error, and when progressing, the first valid state"
                                              "will be requested")

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "configuration_error"

    # make sure you have the last information in the database
    scan = InternetNLV2Scan.objects.all().first()
    progress_running_scan(scan)
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested"

    # configuration_error + retry of requested
    assert InternetNLV2StateLog.objects.all().count() == 5

    # registering has a timeout of a few days, so let's time it out and check for it.
    # The timeout will be fixed next progression.
    update_state(scan, "registering", "This will take too long and time out.")
    scan.last_state_change = datetime.now() - timedelta(days=100)
    scan.save()
    progress_running_scan(scan)
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "timeout"

    # The timeout if fixed and a retry performed. The state is registering again.
    scan = InternetNLV2Scan.objects.all().first()
    progress_running_scan(scan)
    scan = InternetNLV2Scan.objects.all().first()
    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "requested" == scan.state

    # now create another error situation whereby a different recoverable error is used than requested.
    update_state(scan, "running scan", "When an error occurs, a progress will move to running scan, and not to "
                                       "requested")
    update_state(scan, "configuration_error", "oh no!")
    progress_running_scan(scan)

    # recoverable state, error and retry of recoverable state
    assert InternetNLV2StateLog.objects.all().count() == 11

    last = InternetNLV2StateLog.objects.all().last()
    assert last.state == "running scan"
