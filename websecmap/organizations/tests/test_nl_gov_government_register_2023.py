from websecmap.organizations.datasources.nl_gov_government_register_2023 import (
    import_dataset,
)
from websecmap.organizations.datasources.utils import save_succesful_download
from websecmap.organizations.models import OrganizationType, Organization, Url, Coordinate


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def test_import_register_overheidsorganisaties_2023(db):
    location = "websecmap/organizations/tests/nl_gov_government_register/Agentschappen2023.csv"
    dataset = save_succesful_download(
        origin="register_overheidsorganisaties", layer="agentschappen", data=read_file(location)
    )
    # Doing this twice should not deliver extra data
    _import_agentschappen(dataset)
    _import_agentschappen(dataset)


def _import_agentschappen(dataset):
    import_dataset(dataset)

    assert OrganizationType.objects.filter(name="agentschappen").count() == 1
    assert Organization.objects.all().count() == 29
    assert Url.objects.all().count() == 58
    assert Coordinate.objects.all().count() == 29
