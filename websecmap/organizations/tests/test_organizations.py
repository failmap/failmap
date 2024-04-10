from websecmap.organizations.models import Organization, OrganizationType


def test_create_organization(db):
    """Organization can be created."""

    org = Organization(name="test")
    org.save()
    org.layers.add(OrganizationType.objects.get(pk=1))

    assert org
    assert org.name == "test"
    assert org.layers.first().name == "municipality"
