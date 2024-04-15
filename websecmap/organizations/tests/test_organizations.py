from websecmap.organizations.models import Organization, OrganizationType


def test_create_organization(db):
    """Organization can be created."""

    ot = OrganizationType.objects.create(name="municipality")

    org = Organization(name="test")
    org.save()
    org.layers.add(ot)

    assert org
    assert org.name == "test"
    assert org.layers.first().name == "municipality"
