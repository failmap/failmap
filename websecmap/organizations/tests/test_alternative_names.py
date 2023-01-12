from django.utils import timezone

from websecmap.organizations.models import Organization, AlternativeName


def organization_altname(name):
    return AlternativeName.objects.all().filter(name=name).first()


def test_alternative_names(db):

    org = Organization.objects.create(name="Test", created_on=timezone.now())
    org.alternative_names.add(AlternativeName.objects.create(name="Test2"))

    org = Organization.objects.get(alternative_names=organization_altname("Test2"))
    assert org.name == "Test"

    org = Organization.objects.get(alternative_names__name="Test2")
    assert org.name == "Test"
