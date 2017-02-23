from failmap_admin.organizations.models import Organization, OrganizationType


def test_create_organization(db):
    """Organization can be created."""

    org = Organization(name="test", type=OrganizationType.objects.get(pk=1))

    assert org
    assert org.name == 'test'
    assert org.type.name == 'municipality'
