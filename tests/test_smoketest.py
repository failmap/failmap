"""Basic tests to check nothing major is broken."""
import urllib


def test_login_page(live_server):
    """Admin login page should at least return 200."""

    assert urllib.request.urlopen(live_server.url + '/admin').status == 200
