from websecmap.scanners.scanner.cookie_consent import store, store_paper_trail
from websecmap.organizations.models import Url
from websecmap.scanners.models import Cookie, CookieBanner, ExternalResource, CookieScanSession, PaperTrail, Endpoint
from pathlib import Path
import json
from django.core.files.storage import storages
from freezegun import freeze_time
import base64


def test_cookieconsent_store_empty(db):
    url = Url(url="example.com")
    endpoint = Endpoint(url=url, protocol="https")

    result = {}

    store(result, endpoint.id)

    assert not Cookie.objects.all()
    assert not CookieBanner.objects.all()
    assert not ExternalResource.objects.all()
    assert not CookieScanSession.objects.all()
    assert not PaperTrail.objects.all()


def test_cookieconsent_store_tweakers(db):
    url = Url(url="example.com")
    url.save()
    endpoint = Endpoint(url=url, protocol="https")
    endpoint.save()

    # playwright-privacy/ $ make run
    # curl -sf "http://localhost:31337/cookieconsent?site=https://tweakers.net:443&depth=2&maxpages=10" \
    # | jq . > tweakers_result.json
    result = json.loads((Path(__file__).parent / "tweakers_result.json").read_text())

    store(result, endpoint.id)

    assert len(Cookie.objects.all()) == 22
    assert CookieBanner.objects.all()
    assert len(ExternalResource.objects.all()) == 35
    assert not PaperTrail.objects.all()

    session = CookieScanSession.objects.all()[0]
    assert session

    assert len(session.cookies.all()) == 22
    assert len(session.banners.all()) == 1
    assert len(session.external_resources.all()) == 35


@freeze_time("1999-03-24")
def test_cookieconsent_store_paper_trail(db):
    url = Url(url="example.com")
    url.save()
    endpoint = Endpoint(url=url, protocol="https")
    endpoint.save()

    result = {
        "meta": {
            "session_id": 1232384098,
            "paper_trails": {
                "log.txt": base64.b64encode(
                    b"info: visiting page\nwarning: did not find banner\ndebug: found cookie\n"
                ),
                "logs.json": base64.b64encode(b'{"error": "failed to scan page"}'),
            },
        }
    }

    store_paper_trail(result, endpoint.id)

    assert len(PaperTrail.objects.all()) == 2

    assert storages["paper_trail"].size("paper_trail/1999/03-24/cookie_consent/1232384098/logs.json") == 32
    assert storages["paper_trail"].size("paper_trail/1999/03-24/cookie_consent/1232384098/log.txt") == 69
