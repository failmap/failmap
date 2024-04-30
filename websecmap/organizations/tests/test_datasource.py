from websecmap.organizations.datasources import save_organization
from websecmap.organizations.models import OrganizationType, Organization


def test_save_organization(db):
    org = {
        "name": "test",
        "country": "NL",
        "address": "test",
        "lat": 1,
        "lng": 1,
        "dataset": "test",
    }

    orgtype = OrganizationType.objects.create(name="test")

    save_organization(org, orgtype)

    assert Organization.objects.all().count() == 1

    # no crash, just some changed data
    save_organization(org, orgtype)
    assert Organization.objects.all().count() == 1

    # another layer
    orgtype = OrganizationType.objects.create(name="test2")
    save_organization(org, orgtype)
    assert Organization.objects.all().count() == 2
