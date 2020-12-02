import websecmap
from websecmap.organizations.models import Url


def test_add_subdomain(db):
    def mock_resolves(param):
        return True

    websecmap.scanners.scanner.http.resolves = mock_resolves

    u = Url()
    u.url = "example.nl"
    u.save()

    u.add_subdomain("my", internal_notes="Just a friendly test")
    u.save()

    assert Url.objects.all().count() == 2

    new_url = Url.objects.all().get(url="my.example.nl")
    assert new_url.internal_notes == "Just a friendly test"


def test_is_valid_url():

    # This is not going to work as there is a dot in front of the domain.
    # No crashes because of IDNA.
    assert Url.is_valid_url(".espacenet.com") is False
    assert Url.is_valid_url("") is False
    assert Url.is_valid_url("-works.nl") is False

    # Works for domains that are actual domains:
    assert Url.is_valid_url("google.com") is True
    assert Url.is_valid_url("аренда.орг") is True
