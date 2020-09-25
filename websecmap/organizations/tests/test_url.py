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
