"""
Example:
failmap import_organizations excel https://example.com/example.xlsx

Mind the format! See parse_data
"""

import logging

import iso3166
import pyexcel as p

from websecmap.celery import app
from websecmap.organizations.datasources import (download_http_get_no_credentials,
                                                 generic_dataset_import)

log = logging.getLogger(__package__)

datasets = []


def parse_data(dataset, filename):
    """
    The Excel file should contain one tab. The tab contains the following columns:

    Mandatory:
    Name: organization name, using the abbreviation in parenthesis: Awesome Company (AC)
    Address: organization address
    Countrycode: organization country, two letter ISO country code.
    Layer: layer, for example: government, municipality, finance, etc. Will be auto-created.
    Websites (csv): websites (comma separated list of urls)

    Optional:
    Hint: other positional data (used as geocoding hint)
    Lat: optional: latitude, float formatted as "1.0022" (more precision is better)
    Lng: optional: long, float formatted as "1.234" (more precision is better)

    :param dataset:
    :param filename:
    :return:
    """

    # spreadsheet is the best / easiest.
    # csv, ods, xls, xlsx and xlsm files
    found_organizations = []

    log.debug('Loading excel data from %s' % filename)
    sheet = p.get_sheet(file_name=filename, name_columns_by_row=0)
    records = sheet.to_records()

    for record in records:

        validate_record(record)

        sites = record['Websites (csv)'].strip().split(',')
        sites = [x.strip() for x in sites]

        # todo: column numbers might still be easier for people that enter data?
        found_organizations.append(
            {
                'name': record['Name'],
                'address': record['Address'],
                'geocoding_hint': record.get('Hint', ''),
                'websites': sites,
                'country': record['Countrycode'],
                'layer': record['Layer'],
                'lat': record.get('Lat', ''),
                'lng': record.get('Lng', ''),
                'dataset': dataset
            }
        )

    p.free_resources()

    # debug_organizations(found_organizations)

    return found_organizations


def validate_record(record):

    if not record.get('Name', ''):
        ValueError('Missing "Name" column or column was empty.')

    if not record.get('Address', ''):
        ValueError('Missing "Address" column or column was empty.')

    if not record.get('Websites (csv)', ''):
        ValueError('Missing "Websites (csv)" column or column was empty.')

    if not record.get('Countrycode', ''):
        ValueError('Missing "Countrycode" column or column was empty.')

    if not record.get('Layer', ''):
        ValueError('Missing "Layer" column or column was empty.')

    if record['Countrycode'] not in iso3166.countries_by_alpha2:
        raise ValueError('Countrycode is not a valid 3166 country code.')


@app.task(queue='storage')
def import_datasets(**dataset):
    generic_dataset_import(dataset=dataset,
                           parser_function=parse_data,
                           download_function=download_http_get_no_credentials)
