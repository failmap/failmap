import csv
import json
from datetime import datetime
from typing import List, Tuple, Dict, Any

import pytz
import requests
from django.utils import timezone
from django.utils.text import slugify
from requests import RequestException

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.models import Organization, GenericFileDataset, OrganizationType, Coordinate
from django.core.files.uploadedfile import SimpleUploadedFile

GOVERNMENT_REGISTER_FILES = [
    "Gemeenten",
    "Provincies",
    "Waterschappen",
    "Gemeenschappelijke regelingen",
    "Regionale samenwerkingsorganen",
    "Grensoverschrijdende gemeenschappelijke regelingen",
    "Grensoverschrijdende regionale samenwerkingsorganen",
    "Koepelorganisaties",
    "Caribische openbare lichamen",
    "Aruba, Curaçao en Sint Maarten",
    "Openbare lichamen voor beroep en bedrijf",
    "Kabinet van de Koning",
    "Hoge Colleges van Staat",
    "Ministeries",
    "Agentschappen",
    "Interdepartementale commissies",
    "Adviescolleges",
    "Zelfstandige bestuursorganen",
    "Politie en brandweer",
    "Rechtspraak",
]


GOVERNMENT_REGISTER_BASE_URL = "https://organisaties.overheid.nl/export"


def download_government_register_csvs() -> List[int]:

    # todo: how do you know what goes to what layer?
    return [
        download_and_save_dataset(
            f"{GOVERNMENT_REGISTER_BASE_URL}/{file}",
            f"register_overheidsorganisaties_layer_{file}",
            f"register_overheidsorganisaties_layer_{file}_%s.csv",
            slugify(file),
        )
        for file in GOVERNMENT_REGISTER_FILES
    ]


def download_and_save_dataset(
    download_link: str,
    file_format="register_overheidsorganisaties",
    filename="websiteregister_rijksoverheid_%s.ods",
    layer: str = "",
) -> int:
    log.debug(f"Downloading dataset {download_link} into {layer}")
    idataset = GenericFileDataset()
    idataset.file_format = file_format
    idataset.is_imported = False
    idataset.origin = "register_overheidsorganisaties"

    now = datetime.now().isoformat()
    try:
        response = requests.get(download_link)
        idataset.file = SimpleUploadedFile(filename.format(now), response.content)
        idataset.state = "uploaded"
        idataset.parser_info = json.dumps(
            {"origin": "register_overheidsorganisaties", "state": "uploaded", "layer": layer}
        )
    except RequestException as exc:
        idataset.state = "failed_file_download"
        idataset.parser_info = json.dumps(
            {
                "origin": "register_overheidsorganisaties",
                "state": "failed_file_download",
                "exception": exc,
                "layer": layer,
            }
        )
    idataset.save()
    return idataset.id


@app.task(queue="storage")
def download_and_import():
    download_government_register_csvs()
    process_finished_downloads()


def process_finished_downloads():
    files = GenericFileDataset.objects.all().filter(state="uploaded", origin="register_overheidsorganisaties")

    for file in files:
        import_file(file.id)


def import_file(generic_file_dataset_id: int):
    download = GenericFileDataset.objects.all().get(id=generic_file_dataset_id)
    if download.state != "uploaded":
        return

    if not download.parser_info:
        log.warning("No parser information found for dataset %s", generic_file_dataset_id)
        return

    try:
        parser_info = json.loads(download.parser_info)
    except json.JSONDecodeError:
        log.warning(f"Could not parse data from generic file dataset: {download}")
        return
    _ = import_register_overheidsorganisaties(download.file.path, parser_info["layer"])

    # if error_domains:
    #     download.state += f"Amongst failures are: {', '.join(error_domains)}"

    download.is_imported = True
    download.imported_on = datetime.now(pytz.utc)
    download.save()


def import_register_overheidsorganisaties(file_location: str, layer_name: str) -> Tuple[List[str], List[str]]:
    """
    This CSV format is actually huge and contains both organizations, domains and coordinates.
    Any set of an organization name, domain and coordinate is eligible to be added (or updated) on the map.

    Example data:

    """
    layer, _ = OrganizationType.objects.all().get_or_create(name=layer_name)
    with open(file_location, encoding="utf_16_le") as csvfile:
        reader = csv.DictReader(csvfile, quotechar='"', delimiter=";", quoting=csv.QUOTE_ALL)
        for row in reader:
            if row["Internet 1"] and row["Bezoekadres latitude"] and row["Bezoekadres longitude"]:
                insert_or_update_organization(row, layer)


def insert_or_update_organization(row: Dict[str, Any], layer: OrganizationType):
    # This can create an organization or update an existing one with new domains. Domains and data are never deleted
    # for now. If that would be the case: older domains might not be monitored while the government is still responsible
    # for them. This is a hard problem. We could just make this list authoritative which is much easier.
    name = create_name(row)

    organization = Organization.objects.all().filter(name__iexact=name, type=layer).first()

    # add new websites if this already exists.
    if not organization:
        log.debug("Creating new organization: %s", name)
        organization = Organization.objects.create(name=name, type=layer, created_on=timezone.now())

    add_sites(organization, row)

    # Add a coordination if there is none or the current one has changed:
    coordinate = Coordinate.objects.all().filter(organization=organization, is_dead=False).first()
    if not coordinate or coordinate.area != [row["Bezoekadres latitude"], row["Bezoekadres longitude"]]:
        if coordinate:
            coordinate.is_dead = True
            coordinate.save()
        Coordinate.objects.create(
            organization=organization,
            is_dead=False,
            geojsontype="Point",
            area=[row["Bezoekadres latitude"], row["Bezoekadres longitude"]],
        )


def add_sites(organization: Organization, row: Dict[str, Any]):
    """
    Adds sites to the given organization.
    :param organization:
    :param row:
    :return:
    """
    # Most of these organizations have tons of websites...
    sites = [row["Internet 1"], row["Internet 2"], row["Internet 3"]]
    log.debug("Adding sites to organization: %s, %s", organization, sites)
    for site in sites:
        if site:
            organization.add_url(site)


def create_name(row):

    # some evil encoding in the provided files makes everything hard. Because using UTF-8 would be just weird?

    key = "Officiële naam" if "Officiële naam" in row else '\ufeff"Offici\u00eble naam"'
    return f"{row[key]} ({row['Afkorting']})" if row["Afkorting"] else row[key]
