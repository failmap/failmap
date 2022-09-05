import websecmap
from websecmap.organizations.models import Url
from websecmap.scanners.scanner.dns_clean_wildcards import get_identical_sites_on_wildcard_url, compose_scan_task

random = 0


def random_string():
    global random
    random += 1
    return random


def prepare(requests_mock):
    websecmap.scanners.scanner.dns_clean_wildcards.random_string = random_string
    websecmap.scanners.scanner.dns_clean_wildcards.discover_wildcard = lambda x: True

    # Check that the site delivers the same result, passes the 98% the same check
    requests_mock.get("https://1.example.com", text="this is subdomain, this is subdomain, this is subdomain 1")
    requests_mock.get("https://2.example.com", text="this is subdomain, this is subdomain, this is subdomain 2")
    requests_mock.get("https://3.example.com", text="this is subdomain, this is subdomain, this is subdomain 3")
    requests_mock.get("https://4.example.com", text="this is subdomain, this is subdomain, this is subdomain 4")
    requests_mock.get("https://5.example.com", text="this is subdomain, this is subdomain, this is subdomain 5")
    requests_mock.get("https://6.example.com", text="this is subdomain, this is subdomain, this is subdomain 6")
    requests_mock.get("https://7.example.com", text="this is subdomain, this is subdomain, this is subdomain 7")

    # Simulate getting the subdomains and performing the test
    Url(**{"url": "10.example.com"}).save()
    Url(**{"url": "11.example.com"}).save()
    Url(**{"url": "12.example.com"}).save()
    Url(**{"url": "13.example.com"}).save()

    # Check for duplicates
    requests_mock.get("https://10.example.com", text="this is subdomain, this is subdomain, this is subdomain 1")
    requests_mock.get("https://11.example.com", text="this is subdomain, this is subdomain, this is subdomain 1")
    requests_mock.get("https://12.example.com", text="and now for something completely different")
    requests_mock.get("https://13.example.com", text="this is subdomain, this is subdomain, this is subdomain 1")


def test_get_identical_sites_on_wildcard_url(db, requests_mock):
    global random
    random = 0
    prepare(requests_mock)

    identical = get_identical_sites_on_wildcard_url("example.com")
    # primary keys are returned
    assert len(identical) == 3  # [1, 2, 4], id's differ during tests


def test_get_identical_sites_on_wildcard_url_delete(db, requests_mock):
    global random
    random = 0

    # now really delete them:
    prepare(requests_mock)
    Url(**{"url": "example.com"}).save()
    task = compose_scan_task([Url.objects.all().filter(url="example.com").first()])
    task.apply()
    check = Url.objects.all().filter(url="10.example.com").first()
    assert check.is_dead is True
