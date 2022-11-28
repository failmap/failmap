from django.utils import timezone
from freezegun import freeze_time

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.ports import mark_unusual_ports, string_to_list_of_ints
from constance.test.pytest import override_config


def test_ports(db, default_policy, default_scan_metadata):
    with freeze_time("2020-01-01"):
        with override_config(PORTSCAN_SHOULD_BE_INTERNAL_PORTS="1337,4000"):
            url = Url.objects.create(url="internetcleanup.foundation")
            Endpoint.objects.create(url=url, port=80, protocol="123", ip_version=4, discovered_on=timezone.now())
            Endpoint.objects.create(url=url, port=443, protocol="123", ip_version=4, discovered_on=timezone.now())

            # nothing changes
            mark_unusual_ports()

            Endpoint.objects.create(url=url, port=1337, protocol="leet", ip_version=4, discovered_on=timezone.now())
            Endpoint.objects.create(url=url, port=4000, protocol="leet", ip_version=4, discovered_on=timezone.now())

            assert Endpoint.objects.all().count() == 4

            # two scans are added determining a port that should not be open
            mark_unusual_ports()
            assert EndpointGenericScan.objects.all().count() == 2

    # the config changed, 1337 are fine, 4000 also, but 1338 not. Will add two findings
    # do some time traveling as the list of ports is cached for a short duration
    with freeze_time("2020-02-01"):
        with override_config(PORTSCAN_SHOULD_BE_INTERNAL_PORTS="1338"):
            mark_unusual_ports()
            assert EndpointGenericScan.objects.all().count() == 4


def test_string_to_list_of_ints():
    assert string_to_list_of_ints("") == []
    assert string_to_list_of_ints("1") == [1]
    assert string_to_list_of_ints("1,2,3") == [1, 2, 3]
