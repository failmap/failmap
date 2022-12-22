import requests
from constance.test import override_config

from websecmap.organizations.datasources.nl_gov_websiteregister_rijksoverheid import (
    get_rows,
    match_and_place_row,
    import_websiteregister,
    download_websiteregister_spreadsheet,
    find_current_websiteregister_download_link,
)
from websecmap.organizations.models import Url, Organization, GenericFileDataset

location = "websecmap/organizations/tests/nl_gov_rijkswebsiteregister/websiteregister-rijksoverheid-2022-07-28.ods"


def test_get_rows(caplog):
    assert get_rows("") == []
    assert "Unexpected error importing spreadsheet on location" in caplog.text

    data = get_rows(location)

    # Test the 'sheet' itself is not returned, only rows
    # Should skip junk rows
    assert data[0] == ["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"]
    assert len(data) > 200


def test_match_and_place_row(db, caplog):
    # No organizations in the database, so will not be able to find the right one to assign it to.
    match_and_place_row(["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"])
    assert "Could not find" in caplog.text
    assert Url.objects.all().count() == 0

    new_organization = Organization()
    new_organization.name = "Dienst Publiek en Communicatie (DPC/AZ)"
    new_organization.save()

    # This will add www. and the non-wee-wee-wee version of the domain
    match_and_place_row(["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"])
    assert Url.objects.all().count() == 2

    # The same row should not add more urls when importing another time.
    match_and_place_row(["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"])
    match_and_place_row(["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"])
    match_and_place_row(["http://www.rijksoverheid.nl", "Rijksoverheid", "AZ", "DPC", "Online Advies"])
    assert Url.objects.all().count() == 2


def test_import_websiteregister(db):
    # nothing in the database
    error, success = import_websiteregister(location)

    assert error[0] == "www.rijksoverheid.nl"
    assert len(error) > 200
    assert len(success) == 0

    new_organization = Organization()
    new_organization.name = "Dienst Publiek en Communicatie (DPC/AZ)"
    new_organization.save()

    error, success = import_websiteregister(location)

    # www.rijksoverheid.nl has now been added
    assert error[0] == "www.nederlandwereldwijd.nl"
    assert len(error) > 200

    # There are multiple sites managed by DPC/AZ, so multple successes
    assert len(success) == 5
    assert success[0] == "www.rijksoverheid.nl"


def text(filepath: str):
    with open(filepath, "r") as f:
        data = f.read()
    return data


def binary(filepath: str):
    with open(filepath, "rb") as f:
        data = f.read()
    return data


@override_config(
    WEBSITEREGISTER_DOWNLOAD_PAGE="https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/"
    "verplichte-richtlijnen/websiteregister-rijksoverheid",
    WEBSITEREGISTER_SPREADSHEET_FILE_PATTERN_ON_PAGE="binaries\/communicatierijk\/documenten\/publicaties"
    "\/2016\/05\/26\/websiteregister\/websiteregister-rijksoverheid-2...-..-..\.ods",
)
def test_find_current_websiteregister_download_link(db, requests_mock, current_path):
    requests_mock.get(
        "https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/"
        "verplichte-richtlijnen/websiteregister-rijksoverheid",
        text=text(f"{current_path}/websecmap/organizations/tests/nl_gov_rijkswebsiteregister/download_page.html"),
    )

    target = (
        "https://www.communicatierijk.nl/binaries/communicatierijk/documenten/publicaties/"
        "2016/05/26/websiteregister/websiteregister-rijksoverheid-2022-07-28.ods"
    )
    assert find_current_websiteregister_download_link() == target


@override_config(
    WEBSITEREGISTER_DOWNLOAD_PAGE="https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/"
    "verplichte-richtlijnen/websiteregister-rijksoverheid",
    WEBSITEREGISTER_SPREADSHEET_FILE_PATTERN_ON_PAGE="binaries\/communicatierijk\/documenten\/publicaties"
    "\/2016\/05\/26\/websiteregister\/websiteregister-rijksoverheid-2...-..-..\.ods",
)
def test_download_websiteregister_spreadsheet(current_path, db, requests_mock):
    dl_content = text(f"{current_path}/websecmap/organizations/tests/nl_gov_rijkswebsiteregister/download_page.html")
    dl_page = (
        "https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/verplichte-richtlijnen/websiteregister-rijksoverheid"
    )
    spreadsheet_file_link = (
        "https://www.communicatierijk.nl/binaries/communicatierijk/documenten/publicaties/"
        "2016/05/26/websiteregister/websiteregister-rijksoverheid-2022-07-28.ods"
    )
    dl_file = binary(
        f"{current_path}/websecmap/organizations/tests/nl_gov_rijkswebsiteregister/"
        f"websiteregister-rijksoverheid-2022-07-28.ods"
    )

    # Cannot find the url to download stuff...
    requests_mock.get(dl_page, exc=requests.exceptions.ConnectTimeout)
    requests_mock.get(spreadsheet_file_link, exc=requests.exceptions.ConnectTimeout)
    download_websiteregister_spreadsheet()
    assert GenericFileDataset.objects.all().count() == 1
    last = GenericFileDataset.objects.all().last()
    assert last.state == "failed_to_find_spreadsheet_download_url"

    # The url for the download is available, but the download itself is not. So can't download the file.
    requests_mock.get(dl_page, text=dl_content, exc=None)
    requests_mock.get(spreadsheet_file_link, exc=requests.exceptions.ConnectTimeout)
    download_websiteregister_spreadsheet()
    assert GenericFileDataset.objects.all().count() == 2
    first = GenericFileDataset.objects.all().last()
    assert first.file_format == "websiteregister_rijksoverheid"
    assert first.state == "failed_file_download"

    # Now a correct file download, including the file:
    requests_mock.get(dl_page, text=dl_content, exc=None)
    requests_mock.get(spreadsheet_file_link, content=dl_file, exc=None)
    download_websiteregister_spreadsheet()
    assert GenericFileDataset.objects.all().count() == 3
    first = GenericFileDataset.objects.all().last()
    assert first.file_format == "websiteregister_rijksoverheid"
    assert first.state == "uploaded"
