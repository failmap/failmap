import csv
import re
from typing import Any, List

from django.utils.text import slugify

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.datasources.utils import download_dataset_file, finish_import, load_parser_info
from websecmap.organizations.models import GenericFileDataset, OrganizationType
from websecmap.organizations.administration import (
    insert_or_update_organization,
    get_or_create_layer,
    add_urls_to_organization,
    retrieve_possible_urls_from_unfiltered_input,
    insert_or_update_geojson_on_organization,
)

GOVERNMENT_REGISTER_FILES = [
    # "Gemeenten",
    # "Provincies",
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

# These urls are used virtually everywhere. But only one organization is ultimately responsible for such domains.
# So just strip them if we find em...
REDUNDANT_URLS = [
    # Only Dienst Publiek & Communicatie
    "rijksoverheid.nl",
    "www.rijksoverheid.nl",
]

GOVERNMENT_REGISTER_BASE_URL = "https://organisaties.overheid.nl/export"

ORIGIN = "register_overheidsorganisaties"


@app.task(queue="storage")
def download_and_import():
    download()
    import_()


def download():
    for file in GOVERNMENT_REGISTER_FILES:
        download_dataset_file(
            download_link=f"{GOVERNMENT_REGISTER_BASE_URL}/{file}.csv",
            file_format=f"register_overheidsorganisaties_layer_{file}",
            filename=f"register_overheidsorganisaties_layer_{file}_%s.csv",
            layer=slugify(file),
            origin=ORIGIN,
        )


def import_():
    for dataset in GenericFileDataset.objects.all().filter(state="uploaded", origin=ORIGIN, is_imported=False):
        import_dataset(dataset)


def import_dataset(dataset: GenericFileDataset):
    # some defense against pressing import on the wrong file
    if dataset.origin != ORIGIN:
        log.warning("Origin in dataset does not match what we can parse, skipping file.")
        return

    import_records(
        records=get_records_from_file(dataset.file.path),
        layer=get_or_create_layer(load_parser_info(dataset).get("layer", "default")),
    )
    finish_import(dataset)


def get_records_from_file(file_location):
    # Who on earth uses utf_16_le... now we know.
    log.warning("Retrieving records from %s", file_location)
    rows = []
    with open(file_location, encoding="utf_16_le") as csvfile:
        reader = csv.DictReader(csvfile, quotechar='"', delimiter=";", quoting=csv.QUOTE_ALL)
        rows.extend(iter(reader))
    return rows


def import_records(records: Any, layer: OrganizationType):
    log.debug("importing records")
    for row in records:
        geojson_data = extract_geojson_from_row(row)
        organization_name = extract_name_from_row(row)
        sites = extract_sites_from_row(row)
        log.debug("geojson_data: %s, organization_name: %s, sites: %s", geojson_data, organization_name, sites)

        if not sites or not geojson_data[0]:
            continue

        organization = insert_or_update_organization(name=organization_name, layer=layer, country="NL")
        insert_or_update_geojson_on_organization(organization=organization, geojson_data=geojson_data)
        add_urls_to_organization(organization, sites)


def extract_geojson_from_row(row):
    data = row[
        "Adressen (type, toelichting, straat, huisnummer, toevoeging, postbus, postcode, plaats, regio, "
        "provincieAfkorting, land, centroideLatitude, centroideLongitude, centroideRdx, centroideRdy)"
    ]
    # : DR, centroideLatitude: 53.00479338, centroideLongitude: 6.76022075, centr

    matches = re.findall(r"centroideLatitude: ([0-9\.]*), centroideLongitude: ([0-9\.]*), cent", data)
    return [matches[0][0], matches[0][1]] if matches else ["", ""]


def remove_redundant_urls(urls: List[str]) -> List[str]:

    for redundant in REDUNDANT_URLS:
        if redundant in urls:
            urls.remove(redundant)

    return urls


def extract_sites_from_row(row):
    urls, _ = retrieve_possible_urls_from_unfiltered_input(row.get("Internetpagina's", ""))

    # also add the non-www address to the list:
    urls_without_www: List[str] = [url.replace("www.", "") for url in urls if url.startswith("www.")]

    # remove useless urls that are basically added everywhere as a placeholder:
    all_urls = urls_without_www + urls

    return remove_redundant_urls(all_urls)


def extract_name_from_row(row):
    # some evil encoding in the provided files makes everything hard. Because using UTF-8 would be just weird?
    key = "Officiële naam" if "Officiële naam" in row else '\ufeff"Offici\u00eble naam"'

    # Don;t create Gemeente Zutphen (Zutphen)
    if row["Afkorting"] and row["Afkorting"] not in row[key]:
        return f"{row[key]} ({row['Afkorting']})"

    return row[key]
