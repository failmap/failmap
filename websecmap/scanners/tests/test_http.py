from freezegun import freeze_time

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.http import connection_answer, get_random_user_agent, save_endpoint, kill_endpoint


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
