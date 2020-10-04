import pytest
from django.contrib.auth.models import User
from django.test import TestCase

import websecmap
from websecmap.api.apis.sidn import get_map_configuration, sidn_domain_upload, sidn_handle_domain_upload, \
    get_2ndlevel_domains
from websecmap.api.models import SIDNUpload
from websecmap.organizations.models import Url


class ApiTest(TestCase):
    # https://stackoverflow.com/questions/2470634/loading-fixtures-in-django-unit-tests

    fixtures = ["development_scandata.json"]

    @staticmethod
    def test_second_level_list():
        mapconfigs = get_map_configuration()
        assert len(mapconfigs) == 1

        domains = get_2ndlevel_domains('NL', 'municipality')
        assert len(domains) == 6
        assert "arnhem.nl" in domains
        assert sorted(domains) == sorted(
            ['vng.nl', 'zutphen.nl', 'arnhem.nl', 'texel.nl', 'veere.nl', 'vngrealisatie.nl'])


def test_domain_upload(db, requests_mock, current_path):
    # the first answer is cached indefinitely. So the first request has to be correct.

    requests_mock.get(
        "https://publicsuffix.org/list/public_suffix_list.dat",
        text=text(f"{current_path}/public_suffix_list.dat")
    )
    # todo: encoding with 'idna' codec failed (UnicodeError: label empty or too long)  Due to
    # 'www..bergen.nl' There is a problem with parsing domain data. Happens with:
    """
    ,2ndlevel,qname,distinct_asns
    1155,bergen.nl.,surve.bergen.nl.,1
    1823,bergen.nl.,bto.bergen.nl.,1
    2042,bergen.nl.,www.h.bergen.nl.,1
    2167,bergen.nl.,1585059155773.bergen.nl.,1
    """

    u = Url()
    u.url = "arnhem.nl"
    u.save()

    # tldextract does not work correctly in tests. This is a workaround to make sure the computed fileds are set.
    # this is nonsense, since tldexcatct is also used in domain checks. This should work correctly.
    # u.computed_suffix = "nl"
    # u.computed_domain = "arnhem"
    # u.computed_subdomain = ""
    # super(Url, u).save()

    # make sure that the domain is fully present, and that things can be matched.
    # ExtractResult(subdomain='arnhem', domain='nl', suffix=''), suffix should be 'nl'
    new_url = Url.objects.all().get(url="arnhem.nl")
    assert new_url.computed_suffix == "nl"
    assert new_url.computed_domain == "arnhem"
    assert new_url.computed_subdomain == ""

    # mock all requests to arnhem.nl, act like they exist:
    requests_mock.get("", text="1")
    websecmap.scanners.scanner.http.resolves = lambda x: True

    csv_data = """,2ndlevel,qname,distinct_asns
123,arnhem.nl.,*.arnhem.nl.,1
124,arnhem.nl.,01.arnhem.nl.,1
163,arnhem.nl.,01daf671c183434584727ff1c0c29af1.arnhem.nl.,1
2123,arnhem.nl.,www.arnhem.nl.,1
2124,arnhem.nl.,www.h.arnhem.nl.,1
325,arnhem.nl.,14809963d1b7.arnhem.nl.,1"""
    assert SIDNUpload.objects.all().count() == 0
    user = User()
    user.first_name = ""
    user.save()
    sidn_domain_upload(user, csv_data)
    assert SIDNUpload.objects.all().count() == 1

    # Create a domain upload for arnhem:
    sidn_handle_domain_upload(1)

    first_upload = SIDNUpload.objects.first()
    assert first_upload.state == "done"
    assert sorted(first_upload.newly_added_domains) == sorted(
        ["01.arnhem.nl", "01daf671c183434584727ff1c0c29af1.arnhem.nl", "www.arnhem.nl", "14809963d1b7.arnhem.nl"]
    )
    assert first_upload.amount_of_newly_added_domains == 4


def text(filepath: str):
    with open(filepath, "r") as f:
        data = f.read()
    return data
