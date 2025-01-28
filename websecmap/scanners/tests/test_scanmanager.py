from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanmanager import delete_metric_and_set_previous_to_latest


def test_delete_metric_and_set_previous_to_latest(db):
    # preparation
    url = Url.objects.create(url="test.nl")
    ep = Endpoint.objects.create(url=url, port=80, protocol="http")
    kwargs = {"endpoint": ep, "rating_determined_on": datetime.now(timezone.utc)}

    # test: simple case where there is one scan, no previous scan, no other scans:
    epgs = EndpointGenericScan.objects.create(type="test_type", is_the_latest_scan=True, **kwargs)
    delete_metric_and_set_previous_to_latest(epgs)

    # all EndpointsGenericScan objects should be deleted
    assert EndpointGenericScan.objects.count() == 0

    # test: there are three scans of this thing, we'll delete the latest one.
    epgs1 = EndpointGenericScan.objects.create(type="test_type", is_the_latest_scan=False, **kwargs)
    epgs1a = EndpointGenericScan.objects.create(type="test_type_a", is_the_latest_scan=False, **kwargs)
    epgs2 = EndpointGenericScan.objects.create(type="test_type", is_the_latest_scan=False, **kwargs)
    epgs2a = EndpointGenericScan.objects.create(type="test_type_a", is_the_latest_scan=False, **kwargs)
    epgs3 = EndpointGenericScan.objects.create(type="test_type", is_the_latest_scan=True, **kwargs)
    epgs3a = EndpointGenericScan.objects.create(type="test_type_a", is_the_latest_scan=True, **kwargs)
    delete_metric_and_set_previous_to_latest(epgs3)

    # epgs2 should have become the latest, epgs1 should not have been changed
    assert EndpointGenericScan.objects.count() == 5
    assert EndpointGenericScan.objects.get(id=epgs2.id).is_the_latest_scan is True
    assert EndpointGenericScan.objects.get(id=epgs1.id).is_the_latest_scan is False
    # variant tests have not been deleted:
    assert EndpointGenericScan.objects.get(id=epgs1a.id).is_the_latest_scan is False
    assert EndpointGenericScan.objects.get(id=epgs2a.id).is_the_latest_scan is False
    assert EndpointGenericScan.objects.get(id=epgs3a.id).is_the_latest_scan is True
