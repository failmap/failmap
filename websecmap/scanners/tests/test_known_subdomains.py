from websecmap.organizations.models import Url, Organization
from websecmap.scanners.scanner.dns_known_subdomains import compose_discover_task
from websecmap.scanners.scanner.subdomains import get_subdomains, get_popular_subdomains
from celery import group
import logging

log = logging.getLogger(__package__)


def test_get_subdomains(db):
    o, created = Organization.objects.all().get_or_create(name="1", country="NL")

    # Matched per country
    subdomains = ["test", "example", "first", "second"]
    for subdomain in subdomains:
        u, created = Url.objects.all().get_or_create(url=f"{subdomain}.ex.com")
        u.organization.add(o)
        u.save()

    assert get_subdomains(["NL"]) == ["example", "first", "second", "test"]

    assert get_popular_subdomains("NL") == []
    assert get_popular_subdomains("DE") == []

    # Matched per country
    subdomains = ["test", "example", "first", "second"]
    for subdomain in subdomains:
        u, created = Url.objects.all().get_or_create(url=f"{subdomain}.mydomain.com")
        u.organization.add(o)
        u.save()

    assert get_popular_subdomains("NL") == ["example", "first", "second", "test"]
    assert get_popular_subdomains("DE") == []

    # make sure that the task does not crash, and that it's not empty
    tasks = compose_discover_task(list(Url.objects.all()))
    assert tasks is not group()

    # It is intentional that the scans you request, you get. Normally you'd not plan subdomain scans on other
    # subdomains as that would in 99.999% of all cases not make sense.
    wasssw = "websecmap.scanners.scanner.subdomains.wordlist_scan"
    wspf = "websecmap.scanners.plannedscan.finish"
    assert (
        str(tasks) == f"group([{wasssw}([<Url: test.ex.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: test.ex.com>), "
        f"{wasssw}([<Url: example.ex.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: example.ex.com>), "
        f"{wasssw}([<Url: first.ex.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: first.ex.com>), "
        f"{wasssw}([<Url: second.ex.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: second.ex.com>), "
        f"{wasssw}([<Url: test.mydomain.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: test.mydomain.com>), "
        f"{wasssw}([<Url: example.mydomain.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: example.mydomain.com>), "
        f"{wasssw}([<Url: first.mydomain.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: first.mydomain.com>), "
        f"{wasssw}([<Url: second.mydomain.com>], ['example', 'first', 'second', 'test']) "
        f"| {wspf}('discover', 'dns_known_subdomains', <Url: second.mydomain.com>)])"
    )
