import csv
from typing import Any


from django.utils.text import slugify

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.datasources.utils import download_dataset_file, finish_import, load_parser_info
from websecmap.organizations.models import GenericFileDataset, OrganizationType
from websecmap.organizations.administration import (
    insert_or_update_organization,
    get_or_create_layer,
    add_urls_to_organization,
)

GOVERNMENT_REGISTER_FILES = [
    # "Gemeenten",
    # "Provincies",
    # "Waterschappen",
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

        organization = insert_or_update_organization(name=organization_name, layer=layer, geojson_data=geojson_data)
        add_urls_to_organization(organization, sites)


def extract_geojson_from_row(row):
    return [row["Bezoekadres latitude"], row["Bezoekadres longitude"]]


def extract_sites_from_row(row):
    sites = []

    if row["Internet 1"]:
        sites.append(row["Internet 1"])
    if row["Internet 2"]:
        sites.append(row["Internet 2"])
    if row["Internet 3"]:
        sites.append(row["Internet 3"])

    return sites


def extract_name_from_row(row):
    # some evil encoding in the provided files makes everything hard. Because using UTF-8 would be just weird?
    key = "Officiële naam" if "Officiële naam" in row else '\ufeff"Offici\u00eble naam"'
    return f"{row[key]} ({row['Afkorting']})" if row["Afkorting"] else row[key]
