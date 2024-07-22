from websecmap.organizations.datasources.nl_gov_rio_2024 import (
    import_domain_via_organization_surrogate,
    download_single,
)
from websecmap.organizations.models import Organization, OrganizationSurrogateId, Url


def test_import_domain(db):
    # organization: str, domain: str, metadata: dict = None, glossary: str = "nl_gov_rio_2024"
    result = import_domain_via_organization_surrogate(
        "example.nl", "test", {"a": "b"}, "official_organization_name", "nl_gov_rio_2024"
    )

    # organization does not exist, and even if it did, it doesn't have a mapping to a surrogate id
    assert result == {"state": "error", "message": "organization_not_mapped", "domain": "example.nl", "key": "test"}

    # create that mapping and try again, this should work
    o = Organization.objects.create(name="example.nl")
    OrganizationSurrogateId.objects.create(
        organization=o,
        surrogate_id="test",
        used_in_dataset="nl_gov_rio_2024",
        surrogate_id_name="official_organization_name",
    )
    result = import_domain_via_organization_surrogate(
        "example.nl", "test", {"a": "b"}, "official_organization_name", "nl_gov_rio_2024"
    )
    assert result == {"state": "success", "message": "domain_added", "domain": "example.nl", "key": "test"}

    # try again and you'll find that the domain is already in the database,
    # even if you switch key, organization etc. We're not blindly adding domains to multiple organizations.
    #
    result = import_domain_via_organization_surrogate(
        "example.nl", "test", {"a": "b"}, "official_organization_name", "nl_gov_rio_2024"
    )
    assert result == {"state": "error", "message": "domain_already_exists", "domain": "example.nl", "key": "test"}

    # check that metadata is saved in the url and the url is asssociated correctly
    assert Url.objects.get(url="example.nl").internal_notes == '{"a": "b"}'
    assert Url.objects.get(url="example.nl").organization.first() == o


def read_file(path):
    with open(path, "rt") as f:
        return f.read()


def test_download_single(requests_mock, current_path, db):
    url = "https://organisaties.overheid.nl/domeinen/export-domeinnaamregistraties/test.csv"
    answer = read_file(f"{current_path}/websecmap/organizations/tests/nl_gov_rio_2024/testdomeinen.csv")
    requests_mock.get(url, text=answer, status_code=200)

    # Algemene Rekenkamer is in this one
    o = Organization.objects.create(name="testorganization")
    OrganizationSurrogateId.objects.create(
        organization=o,
        surrogate_id="Algemene Rekenkamer",
        used_in_dataset="nl_gov_rio_2024",
        surrogate_id_name="official_organization_name",
    )

    download_single(url)

    assert Url.objects.count() == 8
