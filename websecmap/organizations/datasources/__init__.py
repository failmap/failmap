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
from datetime import datetime, timezone
from os import makedirs, path, rename
from time import sleep, time
from typing import List

import googlemaps
import requests
import tldextract
from constance import config
from django.conf import settings

from websecmap.app.progressbar import print_progress_bar
from websecmap.organizations.models import Coordinate, Dataset, Organization, OrganizationType, Url
from websecmap.scanners.scanner.http import resolves

log = logging.getLogger(__package__)
DOWNLOAD_DIRECTORY = settings.TOOLS["organizations"]["import_data_dir"]
SKIP_GEO = False


def get_data(dataset, download_function):

    # support downloads:
    if dataset["url"]:

        filename = url_to_filename(dataset["url"])
        log.debug("Data will be stored in: %s", filename)

        if is_cached(filename):
            log.debug("Getting cached file for: %s", dataset["url"])
            return filename

        download_function(dataset["url"], filename_to_save=filename)

        log.debug("Filename with data: %s", filename)
        return filename

    # support file uploads
    if dataset["file"]:

        db_dataset = Dataset.objects.all().filter(id=dataset["file"]).first()
        if not db_dataset:
            return ""

        log.debug("Filename with data: %s", db_dataset.file_source.name)
        return settings.MEDIA_ROOT + db_dataset.file_source.name

    return ""


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
    with open(filename, "r", encoding="utf-8") as myfile:
        data = myfile.read()

    return data


def is_cached(filename):
    four_hours_ago = time() - 14400
    if path.isfile(filename) and four_hours_ago < path.getmtime(filename):
        return True
    return False


def url_to_filename(url: str):
    # keep the extension as some importers do magic with that

    md5_hash = hashlib.md5()
    md5_hash.update(f"{url}".encode("utf-8"))

    # make sure the directory for processing files exists
    makedirs(DOWNLOAD_DIRECTORY, exist_ok=True)

    return DOWNLOAD_DIRECTORY + md5_hash.hexdigest() + "." + max(url.split("."))


def check_environment():

    # we may ignore, and geolocate_organizations afterwards the organizations that don't have a geolocation yet?
    # is there are more generic library?
    if not config.GOOGLE_MAPS_API_KEY:
        raise ValueError(
            "The google maps API key is not set, but is required for this feature. Set the "
            "API key in your configuration, "
            '<a target="_blank"  href="/admin/constance/config/">here</a>.'
        )

    # See if the API is usable, it might be restricted (aka, wrong IP etc).
    try:
        gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)
        gmaps.geocode("Rijksmuseum, Amsterdam, The Netherlands")
    except googlemaps.exceptions.ApiError as my_exception:
        raise ValueError(
            "The google API returned an error with a test geolocation query. The error received was:"
            f"{str(my_exception)}. You can configure the google API "
            "<a target='_blank' href='https://console.cloud.google.com/google/maps-apis/"
            "apis/geocoding-backend.googleapis.com/credentials'>here</a>."
        ) from my_exception


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
        if organization["lat"] and organization["lng"]:
            geocoded_addresses.append(organizations)
            continue

        # you can only get the geometry with a lot of data attached, so it cannot be done cheaper :(
        # setup the API restrictions here:
        # https://console.cloud.google.com/google/maps-apis/apis/geocoding-backend.googleapis.com/credentials
        # todo: country code to apply restrictions?
        try:
            log.debug("Geocoding %s", organization["address"])
            geocode_result = gmaps.geocode(f"{organization['address']}, {organization['geocoding_hint']}")

            # give a little slack, so the server is not overburdened. No: its paid for, so just go!
            # sleep(0.03)

        except googlemaps.exceptions.ApiError as my_exception:
            # sometimes the API is just obnoxiously blocking the request, saying the IP is not authorized,
            # while it is.
            # single retry would be enough. Otherwise there are real issues. We don't want to retry a lot because
            # it costs money.
            log.debug("Error received from API, trying again in 10 seconds.")
            log.debug(my_exception)
            sleep(10)

            geocode_result = gmaps.geocode(f"{organization['address']}, {organization['geocoding_hint']}")

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
            lat = geocode_result[0]["geometry"]["location"]["lat"]
            lng = geocode_result[0]["geometry"]["location"]["lng"]
            # log.debug('Received coordinate for %s: lat: %s lng: %s' % (organization['name'], lat, lng))

            print_progress_bar(index, len(organizations), " geo")

            organization["lat"] = lat
            organization["lng"] = lng

        geocoded_addresses.append(organization)

    return geocoded_addresses


def store_data(organizations: List):

    for iteration, organization in enumerate(organizations):
        print_progress_bar(iteration, len(organizations), " store")

        # determine if type exists, if not, create it. Don't waste a nice dataset if the layer is not available.
        organization_type = save_organization_type(organization["layer"])
        failmap_organization = save_organization(organization, organization_type)

        # attach optional coordinate if not exists.
        if organization["lat"] and organization["lng"]:
            save_coordinate(failmap_organization, organization["lat"], organization["lng"], organization["address"])

        save_websites(failmap_organization, organization["websites"])


def download_http_get_no_credentials(url, filename_to_save):
    response = requests.get(url, stream=True, timeout=(1200, 1200))
    response.raise_for_status()

    with open(filename_to_save, "wb") as file_handle:
        filename = file_handle.name
        i = 0
        for chunk in response.iter_content(chunk_size=1024):
            i += 1
            print_progress_bar(1, 100, " download")
            if chunk:  # filter out keep-alive new chunks
                file_handle.write(chunk)

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
            address = f"{extract.subdomain}.{extract.domain}.{extract.suffix}"
            save_url(address, organization)

        address = f"{extract.domain}.{extract.suffix}"
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
            is_dead=False,
        )

        if created:
            coordinate.created_on = datetime.now(timezone.utc)
            coordinate.creation_metadata = address
            coordinate.save(update_fields=["created_on", "creation_metadata"])

    except Coordinate.MultipleObjectsReturned:
        log.debug("Coordinate is multiple times in the database. Unclear which one to fix.")

        # should we reduce the amount of coordinates?

        # coordinate = Coordinate.objects.all().filter(
        #     geojsontype="Point",
        #     organization=organization,
        #     area=[lat, lng],  # we store the order incorrectly it seems?
        #     edit_area={"type": "Point", "coordinates": [lat, lng]},
        #     is_dead=False
        # ).first()


def save_organization(organization, organization_type):
    try:
        failmap_organization, created = Organization.objects.all().get_or_create(
            is_dead=False,
            name=organization["name"],
            type=organization_type,
            country=organization["country"],
        )
    except Organization.MultipleObjectsReturned:
        created = False
        log.debug("Organization %s is multiple times in the database.", organization["name"])
        failmap_organization = (
            Organization.objects.all()
            .filter(
                is_dead=False,
                name=organization["name"],
                type=organization_type,
                country=organization["country"],
            )
            .first()
        )

    # a new organization does not have the created_on fields set. These have to be set.
    changed = False
    if not failmap_organization.surrogate_id and organization.get("surrogate_id", None):
        failmap_organization.surrogate_id = organization.get("surrogate_id", None)
        changed = True

    if not failmap_organization.written_address and organization["address"]:
        failmap_organization.written_address = organization["address"]
        changed = True

    if not failmap_organization.arbitrary_kv_data and organization.get("arbitrary_kv_data", {}):
        failmap_organization.arbitrary_kv_data = organization.get("arbitrary_kv_data", {})
        changed = True

    if not failmap_organization.internal_notes:
        failmap_organization.internal_notes = organization["dataset"]
        changed = True

    if created:
        failmap_organization.created_on = datetime.now(timezone.utc)
        changed = True

    if changed:
        failmap_organization.save()

    # always add the organization to the requested layer
    failmap_organization.layers.add(organization_type)

    return failmap_organization


def save_organization_type(name):
    try:
        organization_type, _ = OrganizationType.objects.all().get_or_create(name=name)
    except OrganizationType.MultipleObjectsReturned:
        log.debug("Layer %s is multiple times in the database.", name)
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
        log.debug("Url %s is multiple times in the database.", website)
        url = Url.objects.all().filter(url=website, is_dead=False).first()

    if created:
        url.created_on = datetime.now(timezone.utc)
        url.internal_notes = "Added using a source importer."

    # the 'if created' results in the same code.
    if not url.organization.all().filter(pk=failmap_organization.pk).exists():
        url.organization.add(failmap_organization)
        url.save()


def debug_organizations(organizations):
    log.debug("This is the current content of all found organizations (%s): ", len(organizations))
    for organization in organizations:
        log.debug(
            "%s, %s, %s, %s, %s",
            organization["name"],
            organization["address"],
            organization["lat"],
            organization["lng"],
            organization["websites"],
        )
