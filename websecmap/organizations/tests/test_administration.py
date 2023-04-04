from datetime import datetime, timedelta, timezone

from websecmap.organizations.administration import (
    force_merge_organizations,
    merge_organizations,
    merge_similar_organizations,
)
from websecmap.organizations.models import AlternativeName, Coordinate, Organization, OrganizationType, Url


def test_merge_similar_organizations(db):
    ot_test = OrganizationType.objects.create(name="test")
    ot_appel = OrganizationType.objects.create(name="appel")

    old_org = Organization.objects.create(name="Test", country="NL", created_on=datetime.now(timezone.utc))
    old_org.alternative_names.add(AlternativeName.objects.create(name="Test3"))
    old_org.layers.add(ot_test)

    # the newer organization has the alt name "Test" which matches the old org.
    new_org = Organization.objects.create(
        name="Iets Anders", country="NL", created_on=datetime.now(timezone.utc), twitter_handle="@ietsanders123"
    )
    new_org.alternative_names.add(AlternativeName.objects.create(name="Test"))
    new_org.layers.add(ot_appel)

    # a much older organizatio with a newer ID (which is weird) is skipped
    Organization.objects.create(name="Test", country="NL", created_on=datetime.now(timezone.utc) - timedelta(days=10))

    assert Organization.objects.all().filter(is_dead=False).count() == 3

    merge_similar_organizations()
    merge_similar_organizations()
    merge_similar_organizations()

    assert Organization.objects.all().filter(is_dead=False).count() == 2


def test_merge_organizations(db):
    ot_test = OrganizationType.objects.create(name="test")
    ot_appel = OrganizationType.objects.create(name="appel")

    old_org = Organization.objects.create(name="Test", country="NL", created_on=datetime.now(timezone.utc))
    old_org.alternative_names.add(AlternativeName.objects.create(name="Test3"))
    old_org.layers.add(ot_test)

    # the newer organization has the alt name "Test" which matches the old org.
    new_org = Organization.objects.create(
        name="Iets Anders", country="NL", created_on=datetime.now(timezone.utc), twitter_handle="@ietsanders123"
    )
    new_org.alternative_names.add(AlternativeName.objects.create(name="Test"))
    new_org.layers.add(ot_appel)

    url = Url.objects.create(url="nu.nl")
    url.organization.add(old_org)
    url.organization.add(new_org)

    url = Url.objects.create(url="example.nl")
    url.organization.add(new_org)

    # The new org has the newer coordinate, this will become the coordinate of organization.
    # so 5/50 will be deleted and 4/40 will be active for old org.
    Coordinate.objects.create(area=["5", "50"], geojsontype="Point", organization=old_org)
    Coordinate.objects.create(area=["4", "40"], geojsontype="Point", organization=new_org)

    merge_organizations(org_from=new_org, org_to=old_org)

    # this should result in the old org having:
    # - the ot_appel layer
    # - the names Iets Anders as an alternative name
    # - the url example.nl in the portfolio
    assert Organization.objects.all().filter(is_dead=False).count() == 1

    assert Organization.objects.all().filter(is_dead=False, alternative_names__name="Iets Anders").count() == 1
    assert Organization.objects.all().filter(is_dead=False, layers__name="appel").count() == 1
    assert Url.objects.all().filter(url="example.nl", organization__name="Test").count() == 1

    firstorg = Organization.objects.all().filter(is_dead=False).first()
    assert firstorg.twitter_handle == "@ietsanders123"

    assert Coordinate.objects.all().filter(is_dead=False).count() == 1
    assert Coordinate.objects.all().filter(is_dead=True).first().organization == old_org
    assert Coordinate.objects.all().filter(is_dead=False).first().organization == old_org
    assert Coordinate.objects.all().filter(is_dead=False).first().area == ["4", "40"]


def test_force_merge_organizations(db):
    now = datetime.now(timezone.utc)
    org1 = Organization.objects.create(name="Test", country="NL", created_on=now)
    org2 = Organization.objects.create(name="Test", country="NL", created_on=now)
    org3 = Organization.objects.create(name="Test", country="NL", created_on=now)
    org4 = Organization.objects.create(name="Test", country="NL", created_on=now)

    # a record that does not merged, to make sure not the entire database is nuked
    Organization.objects.create(name="Test", country="NL", created_on=datetime.now(timezone.utc))
    assert Organization.objects.all().filter(is_dead=False).count() == 5

    force_merge_organizations([org1, org2, org3, org4])

    assert Organization.objects.all().filter(is_dead=False).count() == 2
    assert Organization.objects.all().filter(is_dead=True).count() == 3
    assert Organization.objects.all().filter(is_dead=False).first().created_on == now
