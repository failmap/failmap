# look at surrogate key
# download data as CSV
# process results
from time import sleep

import requests
import csv

import tldextract
from bs4 import BeautifulSoup

from websecmap.app import log
from websecmap.celery import app

# this does not import the metrics, as that should be in a scanner including what happens when there is no metric etc
# todo: make task discoverable
from websecmap.organizations.models import OrganizationSurrogateId, Organization


@app.task(queue="storage", ignore_result=True)
def run():
    keys = OrganizationSurrogateId.objects.all().filter(
        surrogate_id_name="digitoegankelijk", organization__is_dead=False
    )
    for key in keys:
        data = scrape(key.surrogate_id)
        # this will slow down the new requests, so additional rate limiting is not needed
        extract_new_domains(data, key.organization.id)


def scrape(surrogate_id: int):
    # use requests to download the csv file, which is parsed to a dict
    response = requests.get(f"https://dashboard.digitoegankelijk.nl/organisaties/download/{surrogate_id}")

    # parse the csv file
    data = csv.DictReader(response.text.splitlines())
    return list(data)


def extract_new_domains(data: list, organization_id: int):
    # this spreadsheet format is expected to change like 10 times a year, so this code is not rigorously tested
    # and just works for the few months it works. It's useless to expect more.

    address_column = "Adres"
    site_or_app_column = "Site of app"
    status_column = "Status in dashboard"

    """
    Data layout:

    [
        {
            "Adres": "https://www.erfgoedwestland.nl",
            "Site of app": "Site",
            "Status in dashboard": "Some text, like: Z - Verantwoordelijke niet definitief vastgesteld"

            # none of the other data is relevant
        }
    ...
    }
    """

    # These domains host a subdirectory for an organization. The (sub)domain is NOT owned by the organization.
    # rijksoverheid is already owned by someone, so any content over there is owned by someone else.
    # example: magazinesintern.rijksoverheid.nl
    # these are service proviers. Most of them are skipped automatically as they have a path that includes
    # the organization name. eg: https://reppido.nl/citizen/#/oirschot
    # https://www.formdesk.com/gemeenteleusden/ These are suppliers.
    skipped_domains = [
        "archiefweb",
        "royalcast",
        "ndw",
        "rijksoverheid",
        "ilost",
        "octopus",
        "fixi",
        "livestreampartner",
        "vragensociaaldomein",
    ]

    # prevent errors in the dataset
    skipped_domains += [
        "google",
        "linked",
        "microsoft",
        "facebook",
        "instagram",
        "twitter",
        "youtube",
        "instagram",
        "twitter",
        "x",
    ]

    org = Organization.objects.all().filter(id=organization_id).first()
    if not org:
        return

    for row in data:
        if row[site_or_app_column] != "Site":
            continue

        # it's not final that this organization is the owner of that domain
        if row[status_column] == "Z - Verantwoordelijke niet definitief vastgesteld":
            continue

        # subdomains you have to add directly.
        # domains with www. you can add the top level.
        extract = tldextract.extract(row[address_column])

        if extract.domain in skipped_domains:
            continue

        # domain is complete and not an ip address
        if not extract.domain or not extract.suffix:
            continue

        # remove useless pages from the address as that might still be a useful domain
        to_strip = [
            "default.aspx",
            "default.asp",
            "index.php",
            "index.asp",
            "index.html",
            "index.htm",
            "home.php",
            "cms/",
            "home/",
            "Choosemap.aspx",
            "qmaticwebbooking/#/",
        ]
        for s in to_strip:
            row[address_column] = row[address_column].replace(s, "")

        # if the domain has a path we don't want it. More often then not the path is relevant for
        # determining the organization. In that case ownership is centralized.
        # +9 is used for https:// ____ /
        if len(extract.fqdn) + 9 < len(row[address_column]):
            log.debug(f"Skipping {extract.fqdn} as that has a path. {row[address_column]}")
            continue

        if extract.subdomain == "www":
            org.add_url(f"{extract.domain}.{extract.suffix}", origin="digitoegankelijk")

        org.add_url(f"{extract.subdomain}.{extract.domain}.{extract.suffix}", origin="digitoegankelijk")


def list_organiztion_and_ids():
    for i in range(1, 1400):
        response = requests.get(f"https://dashboard.digitoegankelijk.nl/organisaties/{i}")
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip()
        # Zó digitoegankelijk is GGD Twente | Dashboard DigiToegankelijk
        title = title.replace("Zó digitoegankelijk is ", "")
        title = title.replace(" | Dashboard DigiToegankelijk", "")
        print(f"{i}: {title}")

        # be less demanding
        if i % 10 == 0:
            sleep(5)
