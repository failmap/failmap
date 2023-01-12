from datetime import timedelta
from django.utils import timezone

from websecmap.organizations.administration import merge_similar_organizations, merge_organizations
from websecmap.organizations.models import AlternativeName, Organization, OrganizationType, Url


def test_merge_similar_organizations(db):
    ot_test = OrganizationType.objects.create(name="test")
    ot_appel = OrganizationType.objects.create(name="appel")

    old_org = Organization.objects.create(name="Test", country="NL", created_on=timezone.now())
    old_org.alternative_names.add(AlternativeName.objects.create(name="Test3"))
    old_org.layers.add(ot_test)

    # the newer organization has the alt name "Test" which matches the old org.
    new_org = Organization.objects.create(
        name="Iets Anders", country="NL", created_on=timezone.now(), twitter_handle="@ietsanders123"
    )
    new_org.alternative_names.add(AlternativeName.objects.create(name="Test"))
    new_org.layers.add(ot_appel)

    # a much older organizatio with a newer ID (which is weird) is skipped
    Organization.objects.create(name="Test", country="NL", created_on=timezone.now() - timedelta(days=10))

    assert Organization.objects.all().filter(is_dead=False).count() == 3

    merge_similar_organizations()
    merge_similar_organizations()
    merge_similar_organizations()

    assert Organization.objects.all().filter(is_dead=False).count() == 2


def test_merge_organizations(db):

    ot_test = OrganizationType.objects.create(name="test")
    ot_appel = OrganizationType.objects.create(name="appel")

    old_org = Organization.objects.create(name="Test", country="NL", created_on=timezone.now())
    old_org.alternative_names.add(AlternativeName.objects.create(name="Test3"))
    old_org.layers.add(ot_test)

    # the newer organization has the alt name "Test" which matches the old org.
    new_org = Organization.objects.create(
        name="Iets Anders", country="NL", created_on=timezone.now(), twitter_handle="@ietsanders123"
    )
    new_org.alternative_names.add(AlternativeName.objects.create(name="Test"))
    new_org.layers.add(ot_appel)

    url = Url.objects.create(url="nu.nl")
    url.organization.add(old_org)
    url.organization.add(new_org)

    url = Url.objects.create(url="example.nl")
    url.organization.add(new_org)

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
