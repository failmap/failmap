from tldextract import tldextract

import websecmap
from websecmap.organizations.models import Url


def test_add_subdomain(db):
    def mock_resolves(param):
        return True

    websecmap.scanners.scanner.http.resolves = mock_resolves

    u = Url()
    u.url = "example.nl"
    u.save()

    u.add_subdomain("my", origin="Just a friendly test")
    u.save()

    assert Url.objects.all().count() == 2

    new_url = Url.objects.all().get(url="my.example.nl")
    assert new_url.origin == "Just a friendly test"


def test_is_valid_url():

    # This is not going to work as there is a dot in front of the domain.
    # No crashes because of IDNA.
    assert Url.is_valid_url(".espacenet.com") is False
    assert Url.is_valid_url("") is False
    assert Url.is_valid_url("-works.nl") is False

    # Works for domains that are actual domains:
    assert Url.is_valid_url("google.com") is True
    assert Url.is_valid_url("аренда.орг") is True
    assert Url.is_valid_url("something.something.something.орг") is True

    # _jabber._tcp.gmail.com, subdomains can have an underscore, but not hostnames:
    assert Url.is_valid_url("_tcp._mumc.nl") is False
    assert Url.is_valid_url("_tcp.mumc.nl") is True
    assert Url.is_valid_url("_test._tcp.mumc.nl") is True


def test_tldextract():
    # just to know that tldextract is sane:
    extract = tldextract.extract("https://subdomein.basisbeveiliging.co.uk:443/some_page#anchor-13")
    assert extract.fqdn == f"{extract.subdomain}.{extract.domain}.{extract.suffix}"

    extract = tldextract.extract("https://basisbeveiliging.co.uk:443/some_page#anchor-13")
    assert extract.fqdn == f"{extract.domain}.{extract.suffix}"
