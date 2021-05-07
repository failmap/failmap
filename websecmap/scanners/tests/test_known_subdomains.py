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
        # todo: use example.com
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
    assert len(tasks) == 8
    # todo: tasks.tasks
    # assert "websecmap.scanners.scanner.subdomains.wordlist_scan([<Url: test.ex.com>],
    # ['example', 'first', 'second', 'test'])" in str(tasks)

    # It is intentional that the scans you request, you get. Normally you'd not plan subdomain scans on other
    # subdomains as that would in 99.999% of all cases not make sense.
    # wasssw = "websecmap.scanners.scanner.subdomains.wordlist_scan"
    # wspf = "websecmap.scanners.plannedscan.finish"

    # todo: tasks in mysql/postgres tests have other id's. Mysql sequences should be 0 per test.
    # possibly sequence reset needed
    # assert tasks.keys() == ['task', 'args', 'kwargs', 'options', 'subtask_type', 'immutable', 'chord_size']
    # assert tasks.pop('args') == {}
    # print(str(tasks))
    # assert (
    #     str(tasks) == f"group([{wasssw}([{{'id': 1, 'url': 'test.ex.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 1), "
    #     f"{wasssw}([{{'id': 2, 'url': 'example.ex.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 2), "
    #     f"{wasssw}([{{'id': 3, 'url': 'first.ex.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 3), "
    #     f"{wasssw}([{{'id': 4, 'url': 'second.ex.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 4), "
    #     f"{wasssw}([{{'id': 5, 'url': 'test.mydomain.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 5), "
    #     f"{wasssw}([{{'id': 6, 'url': 'example.mydomain.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 6), "
    #     f"{wasssw}([{{'id': 7, 'url': 'first.mydomain.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 7), "
    #     f"{wasssw}([{{'id': 8, 'url': 'second.mydomain.com'}}], ['example', 'first', 'second', 'test']) "
    #     f"| {wspf}('discover', 'dns_known_subdomains', 8)])"
    # )
