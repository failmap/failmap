"""
Importer for Dutch governmental organizations, using open data.

Example:
failmap import_organizations dutch_government

Warning: this is XML, set aside your intuition about programming.

https://almanak-redactie.overheid.nl/archive/
"""

import logging
import xml.etree.ElementTree as ET

from websecmap.celery import app
from websecmap.organizations.datasources import (download_http_get_no_credentials,
                                                 generic_dataset_import, read_data)

log = logging.getLogger(__package__)


def parse_data(dataset, filename):
    data = read_data(filename)
    # this is some kind of XML format. for which an XSD is available.
    # for each document another namespace version is available, which makes it harder.
    # how can we identify the correct namespace for p correctly automatically?
    found_organizations = []

    root = ET.fromstring(data)
    ns = root.attrib['{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'].split(' ')[0]
    log.debug('Using namespace: %s' % ns)

    # of course this doesn't work out the box, so how do we autoregister a namespace?
    ET.register_namespace('p', ns)
    # so just fake / overwrite the namespaces variable
    namespaces = {'p': ns}

    organizations = root.find('p:%s' % dataset['xml_plural'], namespaces)

    # why can't i use a similar construct as get?
    # i want: bla = et.find(x. alaternative if not found)
    for organization in organizations.iterfind('p:%s' % dataset['xml_single'], namespaces):
        name = emulate_get(organization, 'p:naam', namespaces)
        if not name:
            # gemeenschappelijke regelingen has a title, not a name.
            name = emulate_get(organization, 'p:titel', namespaces)

        abbreviation = emulate_get(organization, 'p:afkorting', namespaces)

        contact = organization.find('p:contact', namespaces)
        bezoekAdres = contact.find('p:bezoekAdres', namespaces)
        adres = bezoekAdres.find('p:adres', namespaces)
        straat = emulate_get(adres, 'p:straat', namespaces)
        huisnummer = emulate_get(adres, 'p:huisnummer', namespaces)
        postcode = emulate_get(adres, 'p:postcode', namespaces)
        plaats = emulate_get(adres, 'p:plaats', namespaces)

        site = emulate_get(contact, 'p:internet', namespaces)

        if not postcode and not plaats:
            # try to find something by name... might not have an address...
            geocoding_hint = "%s, Nederland" % name
        else:
            geocoding_hint = "Nederland"

        found_organizations.append(
            {
                'name': "%s (%s)" % (name, abbreviation) if abbreviation else name,
                'address': "%s %s, %s, %s" % (straat, huisnummer, postcode, plaats),
                # make sure that the geocoder is looking at the Netherlands.
                'geocoding_hint': geocoding_hint,
                'websites': [site],
                'country': dataset['country'],
                'layer': dataset['layer'],
                'lat': None,
                'lng': None,
                'dataset': dataset
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


@app.task(queue='storage')
def import_datasets(**dataset):
    generic_dataset_import(dataset=dataset,
                           parser_function=parse_data,
                           download_function=download_http_get_no_credentials)
