from datetime import datetime, timezone

from websecmap.organizations.models import Url, Organization, UrlWhois
from websecmap.scanners.models import UrlGenericScan
from websecmap.scanners.scanner.url.whois import (
    check_ownership,
    get_registrants_for_url,
    regenerate_registrant_statistics_for_all_organizations,
)


def test_check_ownership(db):
    # setup for a usual case where the domain is owned by the right organization
    org = Organization.objects.create(
        name="Gemeente Zutphen",
        country="NL",
        created_on=datetime.now(timezone.utc),
        computed_domain_registrant_statistics={
            "Gemeente Zutphen": {"amount": 2, "urls": ["zutphen.nl, zutphen2.nl"]},
            "Non Legit Hoster": {"amount": 2, "urls": ["zutphen3.nl"]},
        },
        acceptable_domain_registrants=["Gemeente Zutphen"],
    )

    assert UrlGenericScan.objects.all().count() == 0
    check_ownership()
    assert UrlGenericScan.objects.all().count() == 0

    url = Url.objects.create(url="basisbeveiliging.nl")
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="Gemeente Zutphen")
    url.organization.add(org)
    check_ownership()
    first_scan = UrlGenericScan.objects.all().filter(type="whois_domain_ownership").first()
    assert first_scan.rating == "whois_internal_ownership"

    # now check a domain that has a different organization
    url = Url.objects.create(url="nonlegit_basisbeveiliging.nl")
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="Non Legit Hoster 2")
    url.organization.add(org)
    check_ownership()
    last_scan = UrlGenericScan.objects.all().filter(type="whois_domain_ownership").first()
    assert last_scan.rating == "whois_external_ownership"

    # and a domain where there is no registrant information, which is dubious
    url = Url.objects.create(url="hidden_basisbeveiliging.nl")
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="")
    url.organization.add(org)
    check_ownership()
    last_scan = UrlGenericScan.objects.all().filter(type="whois_domain_ownership").first()
    assert last_scan.rating == "whois_unknown_ownership"

    # all different cases
    assert UrlGenericScan.objects.all().count() == 3


def test_regenerate_registrant_statistics_for_all_organizations(db):
    # no crash on dry run:
    regenerate_registrant_statistics_for_all_organizations()

    # now generate these stats
    org = Organization.objects.create(name="Gemeente Zutphen", country="NL", created_on=datetime.now(timezone.utc))
    url = Url.objects.create(url="zutphen.nl")
    url.organization.add(org)
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="Gemeente Zutphen")
    url = Url.objects.create(url="zutphen2.nl")
    url.organization.add(org)
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="Gemeente Zutphen")
    url = Url.objects.create(url="zutphen3.nl")
    url.organization.add(org)
    UrlWhois.objects.create(url=url, is_the_latest=True, registrant="Non Legit Hoster")

    regenerate_registrant_statistics_for_all_organizations()

    org = Organization.objects.get(name="Gemeente Zutphen")
    assert org.computed_domain_registrant_statistics == {
        "Gemeente Zutphen": {"amount": 2, "urls": ["zutphen.nl", "zutphen2.nl"]},
        "Non Legit Hoster": {"amount": 1, "urls": ["zutphen3.nl"]},
    }
    # it was empty, its easier to delete than to add
    assert org.acceptable_domain_registrants == ["Gemeente Zutphen", "Non Legit Hoster"]


def test_get_registrants_for_url(db):
    org1 = Organization.objects.create(
        name="Gemeente Zutphen",
        country="NL",
        created_on=datetime.now(timezone.utc),
        acceptable_domain_registrants=["Gemeente Zutphen"],
    )

    org2 = Organization.objects.create(
        name="Gemeente Zutphen 2",
        country="NL",
        created_on=datetime.now(timezone.utc),
        acceptable_domain_registrants=["Gemeente Zutphen 2"],
    )

    url = Url.objects.create(url="zutphen.nl")
    url.organization.add(org1)
    url.organization.add(org2)

    assert get_registrants_for_url(url) == ["Gemeente Zutphen", "Gemeente Zutphen 2"]
