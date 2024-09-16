from datetime import timezone, datetime
import socket
from urllib.parse import urlparse
from celery import group
from pytest import MonkeyPatch
from pytest_httpserver import HTTPServer
from freezegun import freeze_time
import pytest
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.http import (
    can_connect,
    compose_discover_task,
    connection_answer,
    get_random_user_agent,
    kill_endpoint,
    save_endpoint,
    get_similar_dead_endpoint_in_last_n_days,
    has_acceptable_error,
)


def test_has_acceptable_error():
    # just anything should not be accepted
    assert has_acceptable_error("") is False
    assert has_acceptable_error("some random stuff") is False
    # case insensitive
    assert has_acceptable_error("TLSV1_ALERT_INTERNAL_ERROR") is True
    assert has_acceptable_error("tlsv1_ALERT_INTERNAL_ERROR") is True
    # could contain a lot of data:
    assert has_acceptable_error("some data, something, tlsv1_ALERT_INTERNAL_ERROR, something") is True
    # something from a productio system:
    assert (
        has_acceptable_error(
            "HTTPSConnectionPool(host='www.webportal.spijkenisse.nl', port=443): Max retries exceeded with url: / "
            "(Caused by SSLError(SSLError(1, '[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] sslv3 alert handshake failure"
        )
        is True
    )


def test_connection_answer():
    a = connection_answer()
    assert a == {"result": False, "response_text": "", "error": ""}

    a = connection_answer(True)
    assert a == {"result": True, "response_text": "", "error": ""}

    a = connection_answer(True, TimeoutError("test"))
    assert a == {"result": True, "response_text": "", "error": "TimeoutError"}

    a = connection_answer(True, "error_code")
    assert a == {"result": True, "response_text": "", "error": "error_code"}


def test_get_random_user_agent():
    # randomization lead to unpredictable test results, so it's now just 1
    testdata = {get_random_user_agent() for _ in range(10)}
    assert len(testdata) == 1


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


def test_can_connect_http_standard_port(httpserver: HTTPServer, monkeypatch):
    """A open standard http port should result True."""
    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    httpserver.expect_request("/").respond_with_json({})

    url = urlparse(httpserver.url_for("/"))
    host = url.hostname
    ip = "127.0.0.1"
    port = url.port

    # temporary add the port generated by httpserver to the standard ports
    monkeypatch.setattr("websecmap.scanners.scanner.http.STANDARD_HTTPS_PORTS", [url.port])

    assert can_connect("http", host, port, 4, user_agent="example") == {"result": True, "error": "connect_on_socket"}

    assert can_connect("http", ip, port, 4, user_agent="example") == {"result": True, "error": "connect_on_socket"}


def test_can_connect_http_non_standard_port(httpserver: HTTPServer, monkeypatch):
    """A open non-standard http port that talks http should result True."""
    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    httpserver.expect_request("/").respond_with_json({})

    url = urlparse(httpserver.url_for("/"))
    host = url.hostname
    ip = "127.0.0.1"
    port = url.port

    assert can_connect("http", host, port, 4, user_agent="example") == {
        "error": "found_with_ip",
        "response_text": "200: {}",
        "result": True,
    }

    assert can_connect("http", ip, port, 4, user_agent="example") == {
        "error": "found_with_ip",
        "response_text": "200: {}",
        "result": True,
    }


def test_can_connect_socket_closed_port(httpserver: HTTPServer, monkeypatch):
    """A closed standard http port should result False and a timeout error."""
    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    # reduce timeout to improve test speed
    monkeypatch.setattr("websecmap.scanners.scanner.http.CONNECT_TIMEOUT", 0.1)

    # get a random free port
    sock = socket.socket()
    sock.bind(("localhost", 0))
    port = sock.getsockname()[1]

    # temporary add the free port to the standard ports
    monkeypatch.setattr("websecmap.scanners.scanner.http.STANDARD_HTTPS_PORTS", [port])

    assert not can_connect("http", "localhost", port, 4, user_agent="example")["result"]


def test_can_connect_unresolvable(httpserver: HTTPServer, monkeypatch):
    """A unresolvable address should return false."""

    assert can_connect("https", "1.example.com", 443, 4, user_agent="example") == {
        "error": "ipv4_resolve_error",
        "response_text": "",
        "result": False,
    }


def test_can_connect_http_on_http_port(httpserver: HTTPServer, monkeypatch):
    """Trying to connect with HTTPS on a HTTP server."""
    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    httpserver.expect_request("/").respond_with_json({})

    url = urlparse(httpserver.url_for("/"))
    host = url.hostname
    port = url.port

    result = can_connect("https", host, port, 4, user_agent="example")
    assert not result["result"]
    assert "SSLError" in str(result.get("error"))


@pytest.mark.withoutresponses
def test_http_manual_discover(db, httpserver: HTTPServer, monkeypatch: MonkeyPatch):
    """Test complete endpoint discovery flow, linking both tasks, verifying create and kill."""
    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    url = urlparse(httpserver.url_for("/"))
    host = url.hostname
    port = url.port

    # temporary add the free port to the standard ports
    monkeypatch.setattr("websecmap.scanners.scanner.http.STANDARD_HTTPS_PORTS", [port])

    monkeypatch.setattr("websecmap.scanners.scanner.http.PORT_TO_PROTOCOL", {port: "http"})
    monkeypatch.setattr("websecmap.scanners.scanner.http.PREFERRED_PORT_ORDER", [port])

    url = Url(**{"url": host})
    url.save()

    task = group(compose_discover_task([url]))
    task.apply()

    assert Endpoint.objects.all().count() == 1, "there can be only one"
    endpoint = Endpoint.objects.first()

    assert endpoint.port == port
    assert not endpoint.is_dead
    assert endpoint.url.url == host
    assert endpoint.origin == "ok/http_discover/connect_on_socket"
    assert endpoint.is_ipv4()
    assert not endpoint.is_ipv6()

    httpserver.stop()
    try:
        task = group(compose_discover_task([url]))
        task.apply()
    finally:
        # the httpserver should not bleed over its state between tests, but here we are
        httpserver.start()

    assert Endpoint.objects.all().count() == 1, "there can be only one"
    endpoint = Endpoint.objects.first()

    assert endpoint.is_dead
    assert endpoint.origin == "ok/http_discover/connect_on_socket"
    assert "Connection refused" in endpoint.is_dead_reason


@pytest.mark.withoutresponses
def test_http_manual_discover_non_standard(db, httpserver: HTTPServer, monkeypatch: MonkeyPatch):
    """Test complete endpoint discovery flow, linking both tasks, verifying create and kill."""

    # patch get_ipv4 to allow localhost addresses to be considered global
    monkeypatch.setattr("ipaddress.IPv4Address.is_global", True)

    url = urlparse(httpserver.url_for("/"))
    host = url.hostname
    port = url.port

    monkeypatch.setattr("websecmap.scanners.scanner.http.PORT_TO_PROTOCOL", {port: "http"})
    monkeypatch.setattr("websecmap.scanners.scanner.http.PREFERRED_PORT_ORDER", [port])

    url = Url(**{"url": host})
    url.save()

    task = group(compose_discover_task([url]))
    task.apply()

    assert Endpoint.objects.all().count() == 1, "there can be only one"
    endpoint = Endpoint.objects.first()

    assert endpoint.port == port
    assert not endpoint.is_dead
    assert endpoint.url.url == host
    assert endpoint.origin == "ok/http_discover/found_with_ip"
    assert endpoint.is_ipv4()
    assert not endpoint.is_ipv6()

    httpserver.stop()
    try:
        task = group(compose_discover_task([url]))
        task.apply()
    finally:
        # the httpserver should not bleed over its state between tests, but here we are
        httpserver.start()

    assert Endpoint.objects.all().count() == 1, "there can be only one"
    endpoint = Endpoint.objects.first()

    assert endpoint.is_dead
    assert endpoint.origin == "ok/http_discover/found_with_ip"
    assert "Max retries exceeded with url" in endpoint.is_dead_reason
