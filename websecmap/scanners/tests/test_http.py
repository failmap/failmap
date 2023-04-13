from datetime import timezone, datetime

from freezegun import freeze_time

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.http import (
    can_connect,
    connection_answer,
    get_random_user_agent,
    kill_endpoint,
    save_endpoint,
    get_similar_dead_endpoint_in_last_n_days,
)


def test_connection_answer():

    a = connection_answer()
    assert a == {"result": False, "error": ""}

    a = connection_answer(True)
    assert a == {"result": True, "error": ""}

    a = connection_answer(True, TimeoutError("test"))
    assert a == {"result": True, "error": "TimeoutError"}

    a = connection_answer(True, "error_code")
    assert a == {"result": True, "error": "error_code"}


def test_get_random_user_agent():
    testdata = set()
    for _ in range(0, 200):
        testdata.add(get_random_user_agent())
    assert len(testdata) > 2


def test_save_endpoint(db):
    url = Url(**{"url": "example.com"})
    url.save()

    url_id = Url.objects.all().first().id

    endpoint_1_params = {"protocol": "http", "url_id": url_id, "port": 80, "ip_version": 4, "origin": "test"}

    with freeze_time("2020-01-01"):

        assert Endpoint.objects.all().filter().count() == 0

        save_endpoint(**endpoint_1_params)
        assert Endpoint.objects.all().filter(is_dead=False).count() == 1

        # kill it
        kill_endpoint(**endpoint_1_params)
        assert Endpoint.objects.all().filter(is_dead=True).count() == 1
        assert Endpoint.objects.all().filter(is_dead=False).count() == 0

        # revive it:
        save_endpoint(**endpoint_1_params)
        assert Endpoint.objects.all().filter(is_dead=True).count() == 0
        assert Endpoint.objects.all().filter(is_dead=False).count() == 1

        # save it again: already exists, will not be duplicated:
        save_endpoint(**endpoint_1_params)
        assert Endpoint.objects.all().filter(is_dead=True).count() == 0
        assert Endpoint.objects.all().filter(is_dead=False).count() == 1

        # kill it again:
        kill_endpoint(**endpoint_1_params)

        assert Endpoint.objects.all().filter().count() == 1

    # Travel through time and save it: a new endpoint is made.
    with freeze_time("2021-01-01"):
        save_endpoint(**endpoint_1_params)
        assert Endpoint.objects.all().filter(is_dead=True).count() == 1
        assert Endpoint.objects.all().filter(is_dead=False).count() == 1

        assert Endpoint.objects.all().filter().count() == 2


def test_revive_dead_endpoint(db):
    # guarantee that a dead endpoint for a while ago can be revived;
    url = Url(**{"url": "example.com"})
    url.save()

    # Create an old dead endpoint, this should be revived
    port = 80
    protocol = "http"
    ip_version = 4

    with freeze_time("2020-01-01"):
        ep = Endpoint.objects.create(
            protocol=protocol, url_id=url.id, port=port, is_dead=True, is_dead_since=datetime.now(timezone.utc)
        )
        assert Endpoint.objects.all().filter(is_dead=True).count() == 1
        assert Endpoint.objects.all().filter(is_dead=False).count() == 0

        # we should see this as dead:
        sim = get_similar_dead_endpoint_in_last_n_days(url.id, port, protocol, ip_version)
        assert sim.id == ep.id

    # a year later, we don't see the dead endpoint anymore:
    with freeze_time("2021-01-01"):
        assert None is get_similar_dead_endpoint_in_last_n_days(url.id, port, protocol, ip_version)

    # fourteen days later the old endpoint should have been revived
    with freeze_time("2020-01-14"):

        # we still see the dead endpoint as we're within the "expiration" window:
        sim = get_similar_dead_endpoint_in_last_n_days(url.id, port, protocol, ip_version)
        assert sim.id == ep.id

        save_endpoint(protocol=protocol, url_id=url.id, port=port, ip_version=ip_version, origin="test")
        assert Endpoint.objects.all().filter(is_dead=True).count() == 0
        assert Endpoint.objects.all().filter(is_dead=False).count() == 1


def test_can_connect(requests_mock, mocker):
    mocker.patch("websecmap.scanners.scanner.http.get_ipv4", return_value="127.0.0.1")
    mocker.patch("websecmap.scanners.scanner.http.get_ipv6", return_value="[::1]")

    # test request without positive response, some xception
    assert can_connect("https", "1.example.com", 443, 4) == {
        "result": False,
        "error": "No mock address: GET https://1.example.com:443/",
    }

    # test request via hostname:
    requests_mock.get("https://1.example.com:443/", text="200", status_code=200)
    assert can_connect("https", "1.example.com", 443, 4) == {"result": True, "error": "found_with_hostname"}

    # test request via ip4:
    requests_mock.get("https://127.0.0.1:443/", text="200", status_code=200)
    assert can_connect("https", "1.example.com", 443, 4) == {"result": True, "error": "found_with_ip"}
