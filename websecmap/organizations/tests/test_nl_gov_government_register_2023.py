from websecmap.organizations.datasources.nl_gov_government_register_2023 import import_dataset, remove_redundant_urls
from websecmap.organizations.datasources.utils import save_succesful_download
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url


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
    assert Organization.objects.all().count() == 28
    assert Url.objects.all().count() == 56
    assert Coordinate.objects.all().count() == 28


def test_remove_redundant_urls():
    assert remove_redundant_urls(["basisbeveiliging.nl", "rijksoverheid.nl", "example.nl"]) == [
        "basisbeveiliging.nl",
        "example.nl",
    ]
    assert remove_redundant_urls(["www.rijksoverheid.nl", "rijksoverheid.nl"]) == []
    assert remove_redundant_urls(["basisbeveiliging.nl", "example.nl"]) == ["basisbeveiliging.nl", "example.nl"]
