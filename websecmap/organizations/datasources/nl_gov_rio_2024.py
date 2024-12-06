from typing import Dict, List, Any

from websecmap.app import log
from websecmap.organizations.datasources.nl_gov_websiteregister_rijksoverheid import get_organizations_by_surrogate_key
import requests
import csv
import tldextract
from websecmap.organizations.models import Url
from websecmap.celery import app


@app.task(queue="storagee")
def download_all():
    url = "https://organisaties.overheid.nl/domeinen/export-domeinnaamregistraties/"

    files = [
        "Staten-Generaal",
        "Agentschappen",
        "Ministeries",
        "Inspecties",
        "Adviescolleges",
        "Zelfstandige_bestuursorganen",
        "Politie",
        "Rechtspraak",
    ]

    for file in files:
        download_single(f"{url}{file}.csv")


def download_single(url: str):
    response = requests.get(url, timeout=30)

    if response.status_code != 200:
        log.error("Failed to download from rio %s (status %s)", url, response.status_code)

    data = csv_to_dict(response.content.decode("utf-8"))

    for row in data:
        surrogate = row.pop("Officiële naam organisatie")
        domain = row.pop("domeinnaamregistratie")
        metadata = row
        import_domain_via_organization_surrogate(
            domain, surrogate, metadata, "official_organization_name", "nl_gov_rio_2024"
        )


def csv_to_dict(data: str) -> List[Dict[str, Any]]:
    lines = data.splitlines()
    data = csv.DictReader(lines, quotechar='"', delimiter=";", quoting=csv.QUOTE_ALL)
    return list(data)


def import_domain_via_organization_surrogate(
    domain: str,
    organization: str,
    metadata: dict = None,
    surrogate_id_name: str = "official_organization_name",
    used_in_dataset: str = "nl_gov_rio_2024",
) -> Dict[str, str]:
    # the 'www' prefix does not add anything of value, so remove it.
    domain_extract = tldextract.extract(domain)
    if domain_extract.subdomain == "www":
        domain = f"{domain_extract.domain}.{domain_extract.suffix}"
    else:
        domain = domain_extract.fqdn

    # Now rule 1: make sure it's not in the database yet, as this dataset may associate domains to other organizations
    # over and over. This is not a leading datasource.
    if Url.objects.filter(url=domain).first():
        return {"state": "error", "message": "domain_already_exists", "domain": domain, "key": organization}

    # find the organization that use this surrogate
    organizations = get_organizations_by_surrogate_key(organization, surrogate_id_name, used_in_dataset)

    if not organizations:
        return {"state": "error", "message": "organization_not_mapped", "domain": domain, "key": organization}

    for db_organization in organizations:
        db_organization.add_url(domain, origin="nl_gov_rio_2024", metadata=metadata)

    return {"state": "success", "message": "domain_added", "domain": domain, "key": organization}
