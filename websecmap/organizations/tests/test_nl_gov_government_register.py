from websecmap.organizations.datasources.nl_gov_government_register import (
    import_register_overheidsorganisaties,
    download_government_register_csvs,
    GOVERNMENT_REGISTER_FILES,
    GOVERNMENT_REGISTER_BASE_URL,
)
from websecmap.organizations.models import OrganizationType, Organization, Url, GenericFileDataset
from websecmap.organizations.tests.test_nl_gov_websiteregister_rijksoverheid import binary


def test_import_register_overheidsorganisaties(db):
    location = "websecmap/organizations/tests/nl_gov_government_register/Agentschappen.csv"

    # Doing this twice should not deliver extra data
    _import_agentschappen(location)
    _import_agentschappen(location)

    # todo: check order of lat/lon in database for area
    # Now load a file with the following changes:
    # - move a point
    # - rename an organization
    # - add an extra site to an organization
    # - delete an entire organization
    # - add one extra organization

    # todo: see if all the individual changes are reflected in the database


def _import_agentschappen(location):
    import_register_overheidsorganisaties(location, "agentschappen")

    assert OrganizationType.objects.filter(name="agentschappen").count() == 1
    assert Organization.objects.all().count() == 28
    assert Url.objects.all().count() == 29


def test_download_government_register_csvs(db, requests_mock, current_path):

    for file in GOVERNMENT_REGISTER_FILES:
        requests_mock.get(
            f"{GOVERNMENT_REGISTER_BASE_URL}/{file}",
            content=binary(
                f"{current_path}/websecmap/organizations/tests/nl_gov_government_register/Agentschappen.csv"
            ),
        )

    download_government_register_csvs()

    assert GenericFileDataset.objects.all().count() == 20
