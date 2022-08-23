"""
Importer for Dutch governmental organizations, using open data.

Example:
failmap import_organizations dutch_government

Warning: this is XML, set aside your intuition about programming.

https://almanak-redactie.overheid.nl/archive/
"""

import logging
import xml.etree.ElementTree as ET

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.organizations.datasources import download_http_get_no_credentials, generic_dataset_import, read_data

log = logging.getLogger(__package__)


def parse_data(dataset, filename):
    data = read_data(filename)
    # this is some kind of XML format. for which an XSD is available.
    # for each document another namespace version is available, which makes it harder.
    # how can we identify the correct namespace for p correctly automatically?
    found_organizations = []

    log.debug("Found %s bytes of data in %s.", len(data), filename)

    root = ET.fromstring(data)

    log.debug("Root is now: %s", len(root))
    log.debug(root)

    namespace = root.attrib["{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"].split(" ")[0]
    log.debug("Using namespace: %s", namespace)
    # There is some confusion with getting the namespace with or without S for Security.
    # retrieving gets it without S, but you need it WITH S. Probably a bug in this split code above...
    namespace = namespace.replace("http://", "https://")

    # of course this doesn't work out the box, so how do we autoregister a namespace?
    ET.register_namespace("p", namespace)
    # so just fake / overwrite the namespaces variable
    namespaces = {"p": namespace}

    log.debug(root.get("organisaties"))

    organizations = root.find(f"p:{dataset['xml_plural']}", namespaces)
    log.debug(organizations)

    # why can't i use a similar construct as get?
    # i want: bla = et.find(x. alaternative if not found)
    geocoding_hint = "Nederland"

    for organization in organizations:
        found = {
            "name": emulate_get(organization, "p:naam", namespaces),
            "abbreviation": emulate_get(organization, "p:afkorting", namespaces),
            "contact": organization.find("p:contact", namespaces),
        }

        # log.debug(found)

        if len(found["contact"]):
            found["bezoek_adres"] = found["contact"].find("p:bezoekAdres", namespaces)
            found["adres"] = found["bezoek_adres"].find("p:adres", namespaces)
            found["straat"] = emulate_get(found["adres"], "p:straat", namespaces)
            found["huisnummer"] = emulate_get(found["adres"], "p:huisnummer", namespaces)
            found["postcode"] = emulate_get(found["adres"], "p:postcode", namespaces)
            found["plaats"] = emulate_get(found["adres"], "p:plaats", namespaces)

            found["site"] = emulate_get(found["contact"], "p:internet", namespaces)

            if not found["name"]:
                # gemeenschappelijke regelingen has a title, not a name.
                found["name"] = emulate_get(organization, "p:titel", namespaces)

            if not found["postcode"] and not found["plaats"]:
                # try to find something by name... might not have an address...
                geocoding_hint = f"{found['name']}, Nederland"

            found_organizations.append(
                {
                    "name": f'{found["name"]} ({found["abbreviation"]})' if found["abbreviation"] else found["name"],
                    "address": f'{found["straat"]} {found["huisnummer"]}, {found["postcode"]}, {found["plaats"]}',
                    # make sure that the geocoder is looking at the Netherlands.
                    "geocoding_hint": geocoding_hint,
                    "websites": [found["site"]],
                    "country": dataset["country"],
                    "layer": dataset["layer"],
                    "lat": None,
                    "lng": None,
                    "dataset": dataset,
                }
            )

    # debug_organizations(found_organizations)

    return found_organizations


def emulate_get(xml, element, namespaces):
    # xml.find(element, namespaces) cannot be compared, it's always false.
    # This thus doesn't work:
    # return xml.find(element, namespaces).text if xml.find(element, namespaces) else ""
    try:
        return xml.find(element, namespaces).text
    except AttributeError:
        return ""


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def import_datasets(**dataset):
    generic_dataset_import(
        dataset=dataset, parser_function=parse_data, download_function=download_http_get_no_credentials
    )
