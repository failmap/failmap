import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import requests
import tldextract
from django.core.files.uploadedfile import SimpleUploadedFile
from pyexcel_ods import get_data
from requests import RequestException

from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import GenericFileDataset, Organization


def find_current_websiteregister_download_link() -> str:
    """
    Retrieve the current websiteregister ods file from a configurable location.
    This prevents the need to work with spreadsheets. OTOH working with spreadsheet uploads gives much more
    control but can't be automated properly. It probably will be available for download for years on the
    same page, but with a different filename. It's from 2016 onward the same location.

    I guess you want both, and the spreadsheet upload and the automated process.

    # https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/verplichte-richtlijnen/websiteregister-rijksoverheid

    """
    location = constance_cached_value("WEBSITEREGISTER_DOWNLOAD_PAGE")
    pat = constance_cached_value("WEBSITEREGISTER_SPREADSHEET_FILE_PATTERN_ON_PAGE")

    domain = tldextract.extract(location)

    try:
        data = requests.get(location, timeout=300)
        match = re.findall(pat, data.text)
        if not match:
            return ""

        url = match.pop()
        if not url:
            return ""

        return f"https://{domain.fqdn}/{url}"

    except RequestException as exc:
        log.error("Could not download data from %s. Or pattern did not match: %s", location, pat)
        log.exception(exc)
        return ""


def download_websiteregister_spreadsheet() -> int:
    """
    Retrieve the current websiteregister ods file from a configurable location.
    This prevents the need to work with spreadsheets. OTOH working with spreadsheet uploads gives much more
    control but can't be automated properly. It probably will be available for download for years on the
    same page, but with a different filename. It's from 2016 onward the same location.

    I guess you want both, and the spreadsheet upload and the automated process.

    # https://www.communicatierijk.nl/vakkennis/r/rijkswebsites/verplichte-richtlijnen/websiteregister-rijksoverheid

    """

    idataset = GenericFileDataset()
    idataset.file_format = "websiteregister_rijksoverheid"
    idataset.is_imported = False

    now = datetime.now(timezone.utc).isoformat()

    download_link = find_current_websiteregister_download_link()
    if not download_link:
        idataset.origin = f"Failed to find download url on download page, on {now}."
        idataset.state = "failed_to_find_spreadsheet_download_url"
    else:
        try:
            response = requests.get(download_link, timeout=300)
            idataset.file = SimpleUploadedFile(f"websiteregister_rijksoverheid_{now}.ods", response.content)
            idataset.origin = (
                f"Automatic download from Websiteregister Rijksoverheid, on"
                f" {datetime.now(timezone.utc).isoformat()}."
            )
            idataset.state = "uploaded"
        except RequestException as exc:
            idataset.origin = f"Failed download from Websiteregister Rijksoverheid, on {now}. Exception: {str(exc)}."
            idataset.state = "failed_file_download"

    idataset.save()
    return idataset.id


@app.task(queue="storage")
def download_and_import():
    downloaded_file = download_websiteregister_spreadsheet()
    import_file(downloaded_file)


def import_file(generic_file_dataset_id: int):
    download = GenericFileDataset.objects.all().get(id=generic_file_dataset_id)
    if not download.state == "uploaded":
        return

    error_domains, success_domains = import_websiteregister(download.file.path)
    download.state = f"imported {len(success_domains)} domains sucessfully and {len(error_domains)} failed. "
    if error_domains:
        download.state += f"Amongst failures are: {', '.join(error_domains)}"

    download.is_imported = True
    download.imported_on = datetime.now(timezone.utc)
    download.save()


def import_websiteregister(file_location: str) -> Tuple[List[str], List[str]]:
    rows = get_rows(file_location)
    results = [match_and_place_row(row) for row in rows]

    # give some nice UI feedback about what failed and what was successful
    error_domains = [result["domain"] for result in results if result["state"] == "error"]
    success_domains = [result["domain"] for result in results if result["state"] == "success"]

    return error_domains, success_domains


def get_rows(file_location: str) -> List[List[str]]:
    """
    res = {
        'Sheet1':
            [
                [1797],
                ['URL',
                 'Organisatietype',
                 'Organisatie',
                 'Suborganisatie',
                 'Afdeling'],
                ['http://www.rijksoverheid.nl',
                 'Rijksoverheid',
                 'AZ',
                 'DPC',
                 'Online Advies'],
                ['http://www.nederlandwereldwijd.nl', 'Rijksoverheid', 'BUZA'],
                ['http://coronadashboard.rijksoverheid.nl',
                 'Rijksoverheid',
                 'VWS',
                 '',
                 'Kerndepartement/PDC19']
            ]
        }
    """

    try:
        data = get_data(file_location, start_column=0, column_limit=5)
    except FileNotFoundError:
        log.error("Could not find spreadsheet for import on location: %s", file_location)
        return []
    # Plethora of possible exceptions, for malformed data, io issues, and whatnot.
    except BaseException as exc:  # noqa  # pylint: disable=broad-exception
        log.error("Unexpected error importing spreadsheet on location: %s, error: %s", file_location, str(exc))
        return []

    # The first and second row do not contain domains, the other rows might be useful
    useful_rows = [row for row in data["Sheet1"] if len(row) > 1 and row[0].startswith("http")]

    return useful_rows


def match_and_place_row(row: List[str]) -> Dict[str, str]:
    log.debug("Importing row: %s", row)

    # Example: (DPC/AZ), including braces
    if len(row) > 3:
        # Example: (DPC/AZ), including braces
        organization_key = f"({row[3].strip()}/{row[2].strip()})"
    else:
        # Example: (AZ), including braces
        organization_key = f"({row[2].strip()})"

    # some bug, still adds the / in front. So just remove that slash
    if organization_key[1] == "/":
        organization_key = "(" + organization_key[2 : len(organization_key)]

    domain = row[0].replace("http://", "").replace("https://", "")

    # There should only be one that is currently 'alive'. No there can be more, as there can be multiple maps
    # where this organization is used (and the n-n relation has not yet been implemented).
    organizations = Organization.objects.all().filter(name__icontains=organization_key, is_dead=False)
    if not organizations:
        organizations = Organization.objects.all().filter(
            alternative_names__name__icontains=organization_key, is_dead=False
        )

    if not organizations:
        log.error(
            "Could not find an organization name with key %s, could not place domains %s.", organization_key, domain
        )
        return {"state": "error", "domain": domain, "key": organization_key}

    for organization in organizations:
        organization.add_url(domain, origin="import dutch websiteregister")

        if re.match(r"^www\.", domain):
            without_www = domain.replace("www.", "", 1)
            organization.add_url(without_www, origin="import dutch websiteregister")

    return {"state": "success", "domain": domain, "key": organization_key}
