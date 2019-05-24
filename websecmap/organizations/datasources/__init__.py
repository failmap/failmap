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

import hashlib
import logging
from datetime import datetime
from os import makedirs, path, rename
from time import sleep, time
from typing import List

import googlemaps
import pytz
import requests
import tldextract
from constance import config
from django.conf import settings

from websecmap.app.progressbar import print_progress_bar
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url
from websecmap.scanners.scanner.http import resolves

log = logging.getLogger(__package__)
DOWNLOAD_DIRECTORY = settings.TOOLS['organizations']['import_data_dir']
SKIP_GEO = False


def get_data(dataset, download_function):

    # support downloads:
    if dataset['url']:

        filename = url_to_filename(dataset['url'])
        log.debug("Data will be stored in: %s" % filename)

        if is_cached(filename):
            log.debug('Getting cached file for: %s' % dataset['url'])
            return filename

        download_function(dataset['url'], filename_to_save=filename)

        log.debug('Filename with data: %s' % filename)
        return filename

    # support file uploads
    if dataset['file']:
        log.debug('Filename with data: %s' % dataset['file'].name)
        return settings.MEDIA_ROOT + dataset['file'].name


def generic_dataset_import(dataset, parser_function, download_function):

    check_environment()

    data = get_data(dataset=dataset, download_function=download_function)

    # the parser has to do whatever it takes to parse the data: unzip, read arbitrary nonsense structures and so on
    organizations = parser_function(dataset, data)

    # add geolocation to it
    if not SKIP_GEO:
        organizations = geolocate_organizations(organizations)

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

    # we may ignore, and geolocate_organizations afterwards the organizations that don't have a geolocation yet?
    # is there are more generic library?
    if not config.GOOGLE_MAPS_API_KEY:
        raise ValueError('The google maps API key is not set, but is required for this feature. Set the '
                         'API key in your configuration, '
                         '<a target="_blank"  href="/admin/constance/config/">here</a>.')

    # See if the API is usable, it might be restricted (aka, wrong IP etc).
    try:
        gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)
        gmaps.geocode("Rijksmuseum, Amsterdam, The Netherlands")
    except googlemaps.exceptions.ApiError as e:
        raise ValueError("The google API returned an error with a test geolocation query. The error received was:"
                         "%s. You can configure the google API "
                         "<a target='_blank' href='https://console.cloud.google.com/google/maps-apis/"
                         "apis/geocoding-backend.googleapis.com/credentials'>here</a>." % str(e))


def find_suggested_site(search_string):
    # https://console.cloud.google.com/apis/api/customsearch.googleapis.com/overview
    # uses google custom search (which doesn't have the captchas etc) to find a website using address information
    # note that this result can be WRONG! Yet many/most of the time it's correct.
    # $5 per 1000 queries, up to 10k queries per day. 100 are free.
    # so large datasets cost money as well. oh well.
    # This is only a custom site, and our goal is reversed: we need to find the site matching an address.
    # i can understand why google limits this feature.
    # the BING API is a bit better, resulting in mostly correct results, but not as good as googles.
    pass


def geolocate_organizations(organizations: List):

    # read out once, to prevent a database query every time the variable is needed.
    # note: geocoding costs money(!)
    gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)

    geocoded_addresses = []
    for index, organization in enumerate(organizations):
        # don't do more than one during development:
        # todo: remove
        # if geocoded_addresses:
        #     continue

        # implies the lat/lng are actually correct and valid.
        if organization['lat'] and organization['lng']:
            geocoded_addresses.append(organizations)
            continue

        # you can only get the geometry with a lot of data attached, so it cannot be done cheaper :(
        # setup the API restrictions here:
        # https://console.cloud.google.com/google/maps-apis/apis/geocoding-backend.googleapis.com/credentials
        # todo: country code to apply restrictions?
        try:
            geocode_result = gmaps.geocode("%s, %s" % (organization['address'], organization['geocoding_hint']))

            # give a little slack, so the server is not overburdened.
            sleep(0.1)

        except googlemaps.exceptions.ApiError as e:
            # sometimes the API is just obnoxiously blocking the request, saying the IP is not authorized,
            # while it is.
            # single retry would be enough. Otherwise there are real issues. We don't want to retry a lot because
            # it costs money.
            log.debug('Error received from API, trying again in 10 seconds.')
            log.debug(e)
            sleep(10)

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
        organization_type = save_organization_type(o['layer'])
        failmap_organization = save_organization(o, organization_type)

        # attach optional coordinate if not exists.
        if o['lat'] and o['lng']:
            save_coordinate(failmap_organization, o['lat'], o['lng'], o['address'])

        save_websites(failmap_organization, o['websites'])


def download_http_get_no_credentials(url, filename_to_save):
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


def save_websites(organization, websites: List[str]):
    for website in websites:

        website = website.lower()
        extract = tldextract.extract(website)

        # has to have a valid suffix at least
        if not extract.suffix:
            continue

        # also save the address with subdomain :)
        if extract.subdomain:
            address = "%s.%s.%s" % (extract.subdomain, extract.domain, extract.suffix)
            save_url(address, organization)

        address = "%s.%s" % (extract.domain, extract.suffix)
        save_url(address, organization)


def save_coordinate(organization, lat, lng, address):
    try:
        coordinate, created = Coordinate.objects.all().get_or_create(
            geojsontype="Point",
            organization=organization,
            # order of coordinates in geojson is lng, lat
            # https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem
            area=[lng, lat],
            edit_area={"type": "Point", "coordinates": [lng, lat]},
            is_dead=False
        )

        if created:
            coordinate.created_on = datetime.now(pytz.utc)
            coordinate.creation_metadata = address
            coordinate.save(update_fields=['created_on', 'creation_metadata'])

    except Coordinate.MultipleObjectsReturned:
        log.debug('Coordinate %s is multiple times in the database.' % [lng, lat])

        # should we reduce the amount of coordinates?

        # coordinate = Coordinate.objects.all().filter(
        #     geojsontype="Point",
        #     organization=organization,
        #     area=[lat, lng],  # we store the order incorrectly it seems?
        #     edit_area={"type": "Point", "coordinates": [lat, lng]},
        #     is_dead=False
        # ).first()


def save_organization(o, organization_type):
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

    return failmap_organization


def save_organization_type(name):
    try:
        organization_type, created = OrganizationType.objects.all().get_or_create(name=name)
    except OrganizationType.MultipleObjectsReturned:
        log.debug('Layer %s is multiple times in the database.' % name)
        organization_type = OrganizationType.objects.all().filter(name=name).first()

    return organization_type


def save_url(website, failmap_organization):

    # don't save non resolving urls.
    if not resolves(website):
        return

    # don't stack urls with is_dead=False,
    try:
        url, created = Url.objects.all().get_or_create(
            url=website,
        )
    except Url.MultipleObjectsReturned:
        created = False
        log.debug('Url %s is multiple times in the database.' % website)
        url = Url.objects.all().filter(url=website, is_dead=False).first()

    if created:
        url.created_on = datetime.now(pytz.utc)
        url.internal_notes = "Added using a source importer."

    # the 'if created' results in the same code.
    if not url.organization.all().filter(pk=failmap_organization.pk).exists():
        url.organization.add(failmap_organization)
        url.save()


def debug_organizations(organizations):
    log.debug("This is the current content of all found organizations (%s): " % len(organizations))
    for o in organizations:
        log.debug('%s, %s, %s, %s, %s' % (o['name'], o['address'], o['lat'], o['lng'], o['websites']))
