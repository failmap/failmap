from websecmap.organizations.datasources.nl_gov_government_register import (
    GOVERNMENT_REGISTER_BASE_URL,
    GOVERNMENT_REGISTER_FILES,
    download,
    import_dataset,
)
from websecmap.organizations.datasources.utils import save_succesful_download
from websecmap.organizations.models import Coordinate, GenericFileDataset, Organization, OrganizationType, Url
from websecmap.organizations.tests.test_nl_gov_websiteregister_rijksoverheid import binary


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


# These test cases are kept because it tests the relocation of an organization as well
def test_import_register_overheidsorganisaties(db):
    location = "websecmap/organizations/tests/nl_gov_government_register/Agentschappen.csv"
    dataset = save_succesful_download(
        origin="register_overheidsorganisaties", layer="agentschappen", data=read_file(location)
    )
    # Doing this twice should not deliver extra data
    _import_agentschappen(dataset)
    _import_agentschappen(dataset)

    # todo: check order of lat/lon in database for area
    # Now load a file with the following changes:
    # - move a point: Justis
    # - rename an organization: KNMI
    # - add an extra site to an organization: NFI -> nfi.nl
    # - delete an entire organization: there are a lot less organizations in this file, nothing will be deleted
    #   as this is not an authoritative file
    # - add one extra organization:  Het net iets Betere Nederlands Forensisch Instituut

    # todo: see if all the individual changes are reflected in the database
    location = "websecmap/organizations/tests/nl_gov_government_register/Agentschappen_Mutated.csv"
    dataset = save_succesful_download(
        origin="register_overheidsorganisaties", layer="agentschappen", data=read_file(location)
    )
    import_dataset(dataset)

    # the same
    assert OrganizationType.objects.filter(name="agentschappen").count() == 1

    # +2, betere NFI and KNMI 2.0
    assert Organization.objects.all().count() == 30

    # +1, nfi.nl, plus the domain of knmi 2.0 ofc
    assert Url.objects.all().count() == 30

    # +1, a moved point. plus knmi 2.0 and betere NFI
    assert Coordinate.objects.all().count() == 31
    assert Coordinate.objects.all().filter(is_dead=True).count() == 1


def _import_agentschappen(dataset):
    import_dataset(dataset)

    assert OrganizationType.objects.filter(name="agentschappen").count() == 1
    assert Organization.objects.all().count() == 28
    assert Url.objects.all().count() == 29
    assert Coordinate.objects.all().count() == 28


def test_download_government_register_csvs(db, requests_mock, current_path):

    for file in GOVERNMENT_REGISTER_FILES:
        requests_mock.get(
            f"{GOVERNMENT_REGISTER_BASE_URL}/{file}.csv",
            content=binary(
                f"{current_path}/websecmap/organizations/tests/nl_gov_government_register/Agentschappen.csv"
            ),
        )

    download()

    assert GenericFileDataset.objects.all().count() == 17
