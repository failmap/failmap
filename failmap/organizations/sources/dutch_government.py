"""
Importer for Dutch governmental organizations, using open data.

Example:
failmap import_organizations dutch_government

Warning: this is XML, set aside your intuition about programming.
"""

import logging
import xml.etree.ElementTree as ET
from os import rename

import requests

from failmap.organizations.sources import generic_dataset_import, print_progress_bar, read_data

log = logging.getLogger(__package__)

LAYER = 'government'
COUNTRY = 'NL'

# https://almanak-redactie.overheid.nl/archive/
# the xml plural / single are to help parsing, they don't need to be in your specification.
datasets = [
    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_gemeenschappelijke_regelingen.xml',
     'description': 'Gemeenschappelijke Regelingen', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'gemeenschappelijkeRegelingen', 'xml_single': 'gemeenschappelijkeRegeling'},

    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_organisaties.xml',
     'description': 'Organisaties', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'organisaties', 'xml_single': 'organisatie'},

    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_rechterlijke_macht.xml',
     'description': 'Rechterlijke macht', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'organisaties', 'xml_single': 'organisatie'},

    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_waterschappen.xml',
     'description': 'Waterschappen', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'organisaties', 'xml_single': 'organisatie'},

    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_zelfstandige_bestuursorganen.xml',
     'description': 'Zelfstandige bestuursorganen', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'zelfstandigeBestuursorganen', 'xml_single': 'zelfstandigBestuursorgaan'},

    {'url': 'https://almanak-redactie.overheid.nl/archive/exportOO_ministeries.xml',
     'description': 'Dutch ministries', 'layer': LAYER, 'country': COUNTRY,
     'xml_plural': 'organisaties', 'xml_single': 'organisatie'},
]

namespaces = {
    'p': 'https://almanak.overheid.nl/static/schema/oo/export/2.4.3',
}


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
    namespaces['p'] = ns

    organizations = root.find('p:%s' % dataset['xml_plural'], namespaces)

    # why can't i use a similar construct as get?
    # i want: bla = et.find(x. alaternative if not found)
    for organization in organizations.iterfind('p:%s' % dataset['xml_single'], namespaces):
        name = emulate_get(organization, 'p:naam', namespaces)
        if not name:
            # gemeenschappelijke regelingen...
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


def download(url, filename_to_save):
    # https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console

    # post / get / credentials / protocol, whatever...
    response = requests.get(url, stream=True, timeout=(1200, 1200))
    response.raise_for_status()

    with open(filename_to_save, 'wb') as f:
        filename = f.name
        i = 0
        for chunk in response.iter_content(chunk_size=1024):
            i += 1
            print_progress_bar(1, 100, ' download')
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)

    # save as cachable resource
    # this of course doesn't work if you call it a few times while a download is running, but well, good enough
    rename(filename, filename_to_save)

    return filename_to_save


def import_datasets(**options):
    generic_dataset_import(datasets=datasets, parser_function=parse_data, download_function=download)
