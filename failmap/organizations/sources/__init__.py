"""
Importer functions that make it easy to extend this parser with other datasources.

Note: organizations that are imported have the following format:

{
    'name': str
    'address': str
    # make sure that the geocoder is looking at the Netherlands.
    'geocoding_hint': str,
    'websites': List[str],
    'country': str,
    'layer': str,
    'lat': str,
    'lng': str
}

"""

import logging
import hashlib
from time import time
from os import path, makedirs
from django.conf import settings
from typing import List
from constance import config
import googlemaps
from datetime import datetime
import tldextract
import pytz

from failmap.organizations.models import Organization, OrganizationType, Coordinate, Url

log = logging.getLogger(__package__)
DOWNLOAD_DIRECTORY = settings.TOOLS['organizations']['import_data_dir']
SKIP_GEO = False


def get_data(dataset, download_function):
    filename = url_to_filename(dataset['url'])
    log.debug("Data will be stored in: %s" % filename)

    if is_cached(filename):
        log.debug('Getting cached file for: %s' % dataset['url'])
        return filename

    download_function(dataset['url'], filename_to_save=filename)

    # simply reads and returns the raw data
    return filename


def generic_dataset_import(datasets, parser_function, download_function):

    check_environment()

    for index, dataset in enumerate(datasets):
        log.info('Importing dataset (%s/%s): %s' % (index+1, len(datasets), dataset))
        data = get_data(dataset=dataset, download_function=download_function)

        # the parser has to do whatever it takes to parse the data: unzip, read arbitrary nonsense structures and so on
        organizations = parser_function(dataset, data)

        # add geolocation to it
        if not SKIP_GEO:
            organizations = geolocate(organizations)

        # and finally dump it in the database...
        store_data(organizations)


def read_data(filename):
    with open(filename, 'r') as myfile:
        data = myfile.read()

    return data


def is_cached(filename):
    four_hours_ago = time() - 14400
    if path.isfile(filename) and four_hours_ago < path.getmtime(filename):
        return True


def url_to_filename(url: str):
    # keep the extension as some importers do magic with that

    m = hashlib.md5()
    m.update(("%s" % url).encode('utf-8'))

    # make sure the directory for processing files exists
    makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)

    return DOWNLOAD_DIRECTORY + m.hexdigest() + '.' + max(url.split('.'))


def check_environment():

    # we may ignore, and geolocate afterwards the organizations that don't have a geolocation yet?
    # is there are more generic library?
    if not config.GOOGLE_MAPS_API_KEY:
        raise ValueError('The google maps API key is not set, but is required for this feature.')


def geolocate(organizations: List):

    # read out once, to prevent a database query every time the variable is needed.
    # note: geocoding costs money(!)
    gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)

    geocoded_addresses = []
    for index, organization in enumerate(organizations):
        # don't do more than one during development:
        # todo: remove
        # if geocoded_addresses:
        #     continue

        # you can only get the geometry with a lot of data attached, so it cannot be done cheaper :(
        geocode_result = gmaps.geocode("%s, %s" % (organization['address'], organization['geocoding_hint']))

        """
        [{'address_components': [
            {'long_name': '19', 'short_name': '19', 'types': ['street_number']},
            {'long_name': 'Binnenhof', 'short_name': 'Binnenhof', 'types': ['route']},
            {'long_name': 'Centrum', 'short_name': 'Centrum', 'types': ['political', 'sublocality',
            'sublocality_level_1']},
            {'long_name': 'Den Haag', 'short_name': 'Den Haag', 'types': ['locality', 'political']},
            {'long_name': 'Den Haag', 'short_name': 'Den Haag', 'types': ['administrative_area_level_2', 'political']},
            {'long_name': 'Zuid-Holland', 'short_name': 'ZH', 'types': ['administrative_area_level_1', 'political']},
            {'long_name': 'Netherlands', 'short_name': 'NL', 'types': ['country', 'political']},
            {'long_name': '2513 AA', 'short_name': '2513 AA', 'types': ['postal_code']}],
            'formatted_address': 'Binnenhof 19, 2513 AA Den Haag, Netherlands',
            'geometry': {'location': {'lat': 52.07996809999999, 'lng': 4.3134697},
            'location_type': 'ROOFTOP',
            'viewport': {'northeast': {'lat': 52.0813170802915, 'lng': 4.314818680291502},
            'southwest': {'lat': 52.0786191197085, 'lng': 4.312120719708497}}}, 'place_id':
            'ChIJizsBsCS3xUcR4bqXXEZcdzs',
            'plus_code': {'compound_code': '38H7+X9 The Hague, Netherlands', 'global_code': '9F4638H7+X9'},
            'types': ['street_address']}]
        """
        if geocode_result:
            # let's hope the first result is correct.
            lat = geocode_result[0]['geometry']['location']['lat']
            lng = geocode_result[0]['geometry']['location']['lng']
            # log.debug('Received coordinate for %s: lat: %s lng: %s' % (organization['name'], lat, lng))

            print_progress_bar(index, len(organizations), ' geo')

            organization['lat'] = lat
            organization['lng'] = lng

        geocoded_addresses.append(organization)

    return geocoded_addresses


def store_data(organizations: List):

    for iteration, o in enumerate(organizations):
        print_progress_bar(iteration, len(organizations), ' store')

        # determine if type exists, if not, create it. Don't waste a nice dataset if the layer is not available.
        try:
            organization_type, created = OrganizationType.objects.all().get_or_create(name=o['layer'])
        except OrganizationType.MultipleObjectsReturned:
            log.debug('Layer %s is multiple times in the database.' % o['layer'])
            organization_type = OrganizationType.objects.all().filter(name=o['layer']).first()

        try:
            failmap_organization, created = Organization.objects.all().get_or_create(
                is_dead=False,
                name=o['name'],
                type=organization_type,
                country=o['country'],
            )
        except Organization.MultipleObjectsReturned:
            created = False
            log.debug('Organization %s is multiple times in the database.' % o['name'])
            failmap_organization = Organization.objects.all().filter(
                is_dead=False,
                name=o['name'],
                type=organization_type,
                country=o['country'],
            ).first()

        # a new organization does not have the created_on fields set. These have to be set.
        if created:
            failmap_organization.internal_notes = o['dataset']
            failmap_organization.created_on = datetime.now(pytz.utc)
            failmap_organization.save(update_fields=['created_on'])

        # attach optional coordinate if not exists.
        if o['lat'] and o['lng']:
            try:
                coordinate, created = Coordinate.objects.all().get_or_create(
                    geojsontype="Point",
                    organization=failmap_organization,
                    area=[o['lng'], o['lat']],  # we store the order incorrectly it seems?
                    edit_area={"type": "Point", "coordinates": [o['lng'], o['lat']]},
                    is_dead=False
                )
            except Coordinate.MultipleObjectsReturned:
                created = False
                log.debug('Coordinate %s is multiple times in the database.' % [o['lng'], o['lat']])
                coordinate = Coordinate.objects.all().filter(
                    geojsontype="Point",
                    organization=failmap_organization,
                    area=[o['lng'], o['lat']],  # we store the order incorrectly it seems?
                    edit_area={"type": "Point", "coordinates": [o['lng'], o['lat']]},
                    is_dead=False
                ).first()

            if created:
                coordinate.created_on = datetime.now(pytz.utc)
                coordinate.creation_metadata = o['address']
                coordinate.save(update_fields=['created_on', 'creation_metadata'])

        # blindly add the url, given you're using high quality datasources this is fine. Urls will be killed
        # automatically otherwise.
        for website in o['websites']:

            website = website.lower()
            website = website.replace("https://", "")
            website = website.replace("http://", "")

            extract = tldextract.extract(website)

            # also save the address with subdomain :)
            if extract.subdomain:
                address = "%s.%s.%s" % (extract.subdomain, extract.domain, extract.suffix)
                save_url(address, failmap_organization)

            address = "%s.%s" % (extract.domain, extract.suffix)
            save_url(address, failmap_organization)


def save_url(website, failmap_organization):

    # don't stack urls with is_dead=False,
    try:
        url, created = Url.objects.all().get_or_create(
            url=website,
        )
    except Url.MultipleObjectsReturned:
        log.debug('Url %s is multiple times in the database.' % website)
        url = Url.objects.all().filter(url=website, is_dead=False).first()

    # the 'if created' results in the same code.
    if not url.organization.all().filter(pk=failmap_organization.pk).exists():
        url.organization.add(failmap_organization)
        url.save()


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█'):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end='\r')
    # Print New Line on Complete
    if iteration == total:
        print()


def debug_organizations(organizations):
    log.debug("This is the current content of all found organizations (%s): " % len(organizations))
    for o in organizations:
        log.debug('%s, %s, %s, %s, %s' % (o['name'], o['address'], o['lat'], o['lng'], o['websites']))
