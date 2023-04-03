from datetime import datetime

from freezegun import freeze_time

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import PlannedScan, Scanner, Activity, State
from websecmap.scanners.scanner.nuclei_http import convert_nuclei_data_to_json
from websecmap.scanners.scanner.subdomains_amass import discover, extract_urls_from_json, store, retry_watcher
import websecmap


def get_amass_response(*args):
    mypath = "websecmap/scanners/tests/subdomains_amass/internet.nl.txt"
    with open(mypath, "r") as f:
        return f.read()


def test_amass_discover(monkeypatch):
    monkeypatch.setattr(websecmap.scanners.scanner.subdomains_amass, "call_amass", get_amass_response)
    json_data = discover("example.nl")

    assert json_data[0] == "nl.dev.internet.nl"


def test_extract_urls_from_json():
    data = extract_urls_from_json(convert_nuclei_data_to_json(get_amass_response()))
    assert list(sorted(data)) == list(
        sorted(
            [
                "nl.dev.internet.nl",
                "landkaart.internet.nl",
                "ns.b.qnamemin-test.internet.nl",
                "ipv6.dev.internet.nl",
                "kaart.internet.nl",
                "en.dev.internet.nl",
                "en.conn.dev.internet.nl",
                "www.conn.dev.internet.nl",
                "en.conn.ipv6.internet.nl",
                "nl.conn.ipv6.internet.nl",
                "nl.ipv6.internet.nl",
                "batch.internet.nl",
                "prolodev.internet.nl",
                "internet.nl",
                "www.conn.internet.nl",
                "nl.conn.dev.internet.nl",
                "nl.conn.ipv6.dev.internet.nl",
                "conn.internet.nl",
                "en.batch.internet.nl",
                "1973e58cf26f4abfa80dc16df0a18d4a.a.conn.test-ns-signed.internet.nl",
                "dev.internet.nl",
                "www.internet.nl",
                "8efba613b1af4866a18e6c9bd7986899.a.conn.test-ns-signed.internet.nl",
                "e-mailveilig.internet.nl",
                "0bef0abeeda549fda16dfcc275f0fa79.a.conn.test-ns-signed.internet.nl",
                "6a10b9e7c13e41a78ffd7c2c37532690.a.conn.test-ns-signed.internet.nl",
                "bd953bbf1faf4afd917be364a4f4510a.a.conn.test-ns-signed.internet.nl",
                "toolbox.internet.nl",
                "ipv6.conn.internet.nl",
                "ipv6.internet.nl",
                "nl.conn.internet.nl",
                "www.conn.ipv6.internet.nl",
                "emailveilig.internet.nl",
                "www.dev.internet.nl",
                "en.conn.ipv6.dev.internet.nl",
                "nl.batch.internet.nl",
                "ipv6.conn.dev.internet.nl",
                "en.internet.nl",
                "conn.dev.internet.nl",
                "en.ipv6.internet.nl",
                "www.conn.ipv6.dev.internet.nl",
                "en.ipv6.dev.internet.nl",
                "ns.a.b.qnamemin-test.internet.nl",
                "proloprod.internet.nl",
                "en.conn.internet.nl",
                "nl.ipv6.dev.internet.nl",
                "nl.internet.nl",
                "ipv6kaart.internet.nl",
                "ipv6kaartmetingen.internet.nl",
                "bd953bbf1faf4afd917be364a4f4510a.bogus.conn.test-ns-signed.internet.nl",
                "6a10b9e7c13e41a78ffd7c2c37532690.bogus.conn.test-ns-signed.internet.nl",
                "6d0b03083bee4e6cab29f03eef8f554b.bogus.conn.test-ns-signed.internet.nl",
                "26c363d9e11b4dfc8204fc2a23ac3236.bogus.conn.test-ns-signed.internet.nl",
                "6d0b03083bee4e6cab29f03eef8f554b.a.conn.test-ns-signed.internet.nl",
                "ipv6.dashboard.internet.nl",
                "0bef0abeeda549fda16dfcc275f0fa79.bogus.conn.test-ns-signed.internet.nl",
                "26c363d9e11b4dfc8204fc2a23ac3236.a.conn.test-ns-signed.internet.nl",
                "8efba613b1af4866a18e6c9bd7986899.bogus.conn.test-ns-signed.internet.nl",
                "dashboard.internet.nl",
                "ipv6.acc.dashboard.internet.nl",
                "acc.dashboard.internet.nl",
                "nl.dev.batch.internet.nl",
                "matomo.internet.nl",
                "dev.batch.internet.nl",
                "en.dev.batch.internet.nl",
                "ns.qnamemin-test.internet.nl",
            ]
        )
    )


def test_amass_store(db):
    # organization does not exist, will not cause a crash, will cause a log message
    store(["nl.dev.internet.nl"], 1)

    org = Organization.objects.create(name="test")
    url = Url.objects.create(url="www.example.com")
    url.organization.add(org)

    # add to all organizations that have the www.example.com url
    store(["nl.dev.internet.nl"], url.id)

    assert Url.objects.count() == 2
    assert Url.objects.get(url="nl.dev.internet.nl").organization.all().first().id == org.id


def test_retry_watcher(db):
    # nothing should happen, no crash:
    retry_watcher()

    scanner = Scanner.objects.create(name="subdomains_amass", python_name="subdomains_amass", enabled=True)
    url = Url.objects.create(url="www.example.com")

    # create a scan that should not be reset because it has not expired:
    with freeze_time("2020-01-01 12:00"):
        PlannedScan.objects.create(
            scanner=scanner,
            activity=Activity.discover,
            state=State.picked_up,
            url=url,
            requested_at_when=datetime(2020, 1, 1, 12),
            last_state_change_at=datetime(2020, 1, 1, 12),
        )

        retry_watcher()
        assert PlannedScan.objects.first().state == State.picked_up
        # reset for the next test.
        PlannedScan.objects.all().delete()

        # now make an expired scan, an hour ago.
        PlannedScan.objects.create(
            scanner=scanner,
            activity=Activity.discover,
            state=State.picked_up,
            url=url,
            requested_at_when=datetime(2020, 1, 1, 11),
            last_state_change_at=datetime(2020, 1, 1, 11),
        )

        retry_watcher()
        assert PlannedScan.objects.first().state == State.requested
        assert PlannedScan.objects.first().state != State.picked_up
        PlannedScan.objects.all().delete()
