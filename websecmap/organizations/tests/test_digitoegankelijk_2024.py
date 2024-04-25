import pathlib

from websecmap.organizations.datasources.digitoegankelijk_2024 import parse, extract_new_domains
from websecmap.organizations.models import Organization, Url


def test_digitoegankelijk_parse(current_path):
    file_1 = f"{current_path}/websecmap/organizations/tests/digitoegankelijk_2024/export_gemeente_westland_25042024.csv"

    data = pathlib.Path(file_1).read_text()
    parsed = parse(data)
    assert parsed[0] == {
        "Aantal succescriteria waaraan wordt voldaan": "22",
        "Adres": "https://www.erfgoedwestland.nl",
        "Naam/URL": "Erfgoed Westland",
        "Opmerking": "voorlopige status",
        "Site of app": "Site",
        "Status in dashboard": "B - Voldoet gedeeltelijk",
        "Totaal aantal succescriteria": "50",
    }


def test_extract_new_domains(current_path, db):
    file_1 = f"{current_path}/websecmap/organizations/tests/digitoegankelijk_2024/export_gemeente_westland_25042024.csv"
    data = pathlib.Path(file_1).read_text()
    parsed = parse(data)

    assert len(parsed) == 23

    # the Z domains are not added... apps are also not added
    org = Organization.objects.create(name="test")
    fine_for_this_run = extract_new_domains(parsed, org.id, [])
    assert Url.objects.all().filter(organization=org).count() == 20

    # make sure that the domain is not added anymore to other organizations
    org_2 = Organization.objects.create(name="test 2")
    extract_new_domains(parsed, org_2.id, [])
    assert Url.objects.all().filter(organization=org_2).count() == 0

    # it's fine when it's in the same run:
    extract_new_domains(parsed, org_2.id, fine_for_this_run)
    assert Url.objects.all().filter(organization=org_2).count() == 20
