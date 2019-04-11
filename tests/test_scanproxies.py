import requests
import json

from websecmap.scanners.logic.scanproxy import import_proxies_by_country
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner.tls_qualys import check_proxy

# mock result: https://api.openproxy.space/short/country/%s?limit=50&skip=%s&ts=%s


def file_get_contents(filepath):
    with open(filepath, 'r') as content_file:
        return content_file.read()


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, content, status_code):
            self.content = content
            self.status_code = status_code
            self.json = lambda: json.loads(self.content)

    if args[0].startswith('https://api.openproxy.space/country/'):
        return MockResponse(file_get_contents('tests/scanproxy/proxies.json').encode(), 200)

    return MockResponse(None, 404)


def test_scanproxies(db, monkeypatch):

    monkeypatch.setattr(requests, 'get', mocked_requests_get)
    # don't create tasks or invoke celery

    monkeypatch.setattr(check_proxy, 'apply_async', lambda x: True)
    import_proxies_by_country(countries=['NL'], amount=50)

    assert ScanProxy.objects.all().count() == 15
