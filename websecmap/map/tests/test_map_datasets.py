# Create your tests here.
import logging

# from unittest import mock
from django.utils import timezone

from websecmap.map.logic.datasets import export_urls_only
from websecmap.organizations.models import Organization, OrganizationType, Url

log = logging.getLogger(__package__)


def file_get_contents(filepath):
    with open(filepath, "r") as content_file:
        return content_file.read()


# New urls use tldextract. This sometimes performs a call to the latest public suffixes list as it updates frequently.
# We mock that response to the test logs don't get polluted.
def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, content, status_code):
            self.content = content
            self.status_code = status_code

    if args[0] == "https://publicsuffix.org/list/public_suffix_list.dat":
        return MockResponse(file_get_contents("mocked_http_responses/public_suffix_list.dat").encode(), 200)

    return MockResponse(None, 404)


# If you enable mock.patch, the db fixture for pytest as a function aregument is ignored (counterintuitively)
# Therefore we have to explicitly add it. Note that a pytest fixture is data. While we need db access.
# Failed: Database access not allowed, use the "django_db" mark, or the "db" or "transactional_db" fixtures to enable it
# @mock.patch('requests.get', side_effect=mocked_requests_get)
def test_map_datasets(db):

    organization_type, created = OrganizationType.objects.all().get_or_create(name="municipality")

    organization, created = Organization.objects.all().get_or_create(
        name="test", type=organization_type, country="NL", created_on=timezone.now(), is_dead=False
    )

    url, created = Url.objects.all().get_or_create(
        url="test.nl", created_on=timezone.now(), is_dead=False, not_resolvable=False
    )

    # create the n-n connection between url and organization
    url.organization.add(organization)
    url.save()

    url, created = Url.objects.all().get_or_create(
        url="test2.nl", created_on=timezone.now(), is_dead=False, not_resolvable=False
    )

    # create the n-n connection between url and organization
    url.organization.add(organization)
    url.save()

    url, created = Url.objects.all().get_or_create(
        url="test3.nl", created_on=timezone.now(), is_dead=False, not_resolvable=False
    )
    # create the n-n connection between url and organization
    url.organization.add(organization)
    url.save()

    # test a complete flow
    # we should now be able to export a dataset with a single url
    # The return is a string(!)
    book = export_urls_only("NL", "municipality")

    # there is a filename
    assert book["data"][1, 1] == "test.nl"
    assert book["data"][2, 1] == "test2.nl"
    assert book["data"][3, 1] == "test3.nl"
