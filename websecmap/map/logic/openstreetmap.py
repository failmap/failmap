import json
import logging
import os.path
import re
import subprocess
import time
import zipfile
from datetime import datetime
from subprocess import CalledProcessError
from typing import Dict, List

import pytz
import requests
import tldextract
from constance import config
from django.conf import settings
from django.utils import timezone
from django.utils.safestring import mark_safe
from iso3166 import countries
from rdp import rdp

from websecmap.app.progressbar import print_progress_bar
from websecmap.celery import app
from websecmap.map.logic.wikidata import (ISO3316_2_COUNTRY_CODE, ISO3316_2_COUNTY_SUBDIVISION_CODE,
                                          OFFICIAL_WEBSITE, get_property_from_code)
from websecmap.map.models import AdministrativeRegion
from websecmap.organizations.models import Coordinate, Organization, OrganizationType

log = logging.getLogger(__package__)

DEFAULT_RESAMPLING_RESULUTION = 0.001

"""
Todo: Possibility to remove water:
https://stackoverflow.com/questions/25297811/how-can-i-remove-water-from-openstreetmap-ways
https://gis.stackexchange.com/questions/157842/how-to-get-landmass-polygons-for-bounding-box-in-overpass-api/157943
https://stackoverflow.com/questions/41723087/get-administrative-borders-with-overpass-ql
"""


def get_resampling_resolution(country: str = "NL", organization_type: str = "municipality"):
    resolution = AdministrativeRegion.objects.all().filter(
        country=country,
        organization_type__name=organization_type).values_list('resampling_resolution', flat=True).first()
    return resolution if resolution else DEFAULT_RESAMPLING_RESULUTION


def get_region(country: str = "NL", organization_type: str = "municipality"):
    return AdministrativeRegion.objects.all().filter(
        country=country,
        organization_type__name=organization_type
    ).values_list('admin_level', flat=True).first()


# making this atomic makes sure that the database is locked in sqlite.
# The transaction is very very very very very very very very very very long
# You also cannot see progress...
# better to validate that the region doesn't exist and then add it...
# @transaction.atomic
@app.task(queue="storage")
def import_from_scratch(countries: List[str] = None, organization_types: List[str] = None, when=None):
    """
    Run this when you have nothing on the organization type in that country. It will help bootstrapping a
    certain region.

    :param countries: uppercase list of 2-letter country codes.
    :param organization_types: the types you want to import.
    :param when:
    :return:
    """

    log.info(f"Countries: {countries}")
    log.info(f"Region(s): {organization_types}")

    if not countries or countries == [None]:
        countries = ["NL"]

    # paramter hate causes organization_types == [None]
    if not organization_types or organization_types == [None]:
        log.info("Going to get all existing organization types, and try to import them all.")
        organization_types = list(OrganizationType.objects.all().values_list('name', flat=True))

    for country in sorted(countries):
        for organization_type in sorted(organization_types):

            if not get_region(country, organization_type):
                log.info(f"The combination of {country} and {organization_type} does not exist in OSM. Skipping.")
                continue

            try:
                store_import_message(country, organization_type, "Downloading data")
                if config.WAMBACHERS_OSM_CLIKEY:
                    data = get_osm_data_wambachers(country, organization_type)
                else:
                    data = get_osm_data(country, organization_type)
            except requests.exceptions.HTTPError as ex:
                store_import_message.apply_async([country, organization_type, ex])
                continue

            for index, feature in enumerate(data["features"]):

                if "properties" not in feature:
                    continue

                if "name" not in feature["properties"]:
                    continue

                resolution = get_resampling_resolution(country, organization_type)
                resampled = resample(feature, resolution)
                store_new(resampled, country, organization_type, when)
                message = "Imported %s of %s. %s%% (Currently: %s)" % (
                    index+1,
                    len(data["features"]),
                    round(((index+1)/len(data["features"]))*100, 2),
                    feature["properties"]["name"])
                store_import_message(country, organization_type, message)

                # can't do multiprocessing.pool, given non global functions.
            store_import_message(country, organization_type, "Import complete. To view your import, go to "
                                                             "<a href='../configuration/'>map configuration</a> "
                                                             "and set this to display. Reports are generated in "
                                                             "the background. On first import everything imported"
                                                             " will look gray.")

    log.info("Import finished.")


@app.task(queue="storage")
def store_import_message(country, organization_type, message):
    # Note, that AdministrativeRegion is written to an old copy of this object in the task chain
    # after import is performed. Therefore explicitly set the update field, so not to lose other data.

    log.debug(f"Update message received for ({country}/{organization_type}): {message}")

    region = AdministrativeRegion.objects.filter(
        country=country,
        organization_type__name=organization_type).first()

    region.import_message = mark_safe(str(message)[0:240])
    region.save(update_fields=['import_message'])


# @transaction.atomic
@app.task(queue="storage")
def update_coordinates(countries: List[str] = None, organization_types: List[str] = None, when=None):

    if not osmtogeojson_available():
        raise FileNotFoundError("osmtogeojson was not found. Please install it and make sure python can access it. "
                                "Cannot continue.")

    for country in sorted(countries):
        for organization_type in sorted(organization_types):

            log.info(f"Attempting to update coordinates for: {country} {organization_type}.")

            # you are about to load 50 megabyte of data. Or MORE! :)
            try:
                store_import_message(country, organization_type, "Downloading data")
                if config.WAMBACHERS_OSM_CLIKEY:
                    data = get_osm_data_wambachers(country, organization_type)
                else:
                    data = get_osm_data(country, organization_type)
            except requests.exceptions.HTTPError as ex:
                store_import_message.apply_async([country, organization_type, ex])
                return

            log.info(f"Received coordinate data. Starting with: {json.dumps(data)[0:200]}")

            log.info("Parsing features:")
            for index, feature in enumerate(data["features"]):

                if "properties" not in feature:
                    log.debug("Feature misses 'properties' property :)")
                    continue

                if "name" not in feature["properties"]:
                    log.debug("This feature does not contain a name: it might be metadata or something else.")
                    continue

                # slower, but in a task. Still atomic this way.
                resolution = get_resampling_resolution(country, organization_type)
                store_updates(resample(feature, resolution), country, organization_type, when)
                message = "Updated %s of %s. %s%% (Currently: %s)" % (
                    index + 1,
                    len(data["features"]),
                    round(((index + 1) / len(data["features"])) * 100, 2),
                    feature["properties"]["name"])
                store_import_message(country, organization_type, message)

            store_import_message(country, organization_type, "Update complete")

    log.info("Resampling and update tasks have been created.")


def resample(feature: Dict, resampling_resolution: float = 0.001):
    # downsample the coordinates using the rdp algorithm, mainly to reduce 50 megabyte to a about 150 kilobytes.
    # The code is a little bit dirty, using these counters. If you can refactor, please do :)

    log.info(f"Resampling path for {feature['properties']['name']}")

    if feature["geometry"]["type"] == "Polygon":
        log.debug("Original length: %s" % len(feature["geometry"]["coordinates"][0]))
        i = 0
        for coordinate in feature["geometry"]["coordinates"]:
            feature["geometry"]["coordinates"][i] = rdp(coordinate, epsilon=resampling_resolution)
            i += 1
        log.debug("Resampled length: %s" % len(feature["geometry"]["coordinates"][0]))

    if feature["geometry"]["type"] == "MultiPolygon":
        i, j = 0, 0
        for coordinate in feature["geometry"]["coordinates"]:
            for nested_coordinate in feature["geometry"]["coordinates"][i]:
                feature["geometry"]["coordinates"][i][j] = rdp(nested_coordinate, epsilon=resampling_resolution)
                j += 1

            j = 0
            i += 1

    return feature


def store_new(feature: Dict, country: str = "NL", organization_type: str = "municipality", when=None):
    properties = feature["properties"]
    coordinates = feature["geometry"]

    """
    Handles the storing / administration of coordinates in failmap using the stacking pattern.

    "properties": {
                "@id": "relation/47394",
                "admin_level": "8",
                "authoritative": "yes",
                "boundary": "administrative",
                "name": "Heemstede",
                "ref:gemeentecode": "397",
                "source": "dataportal",
                "type": "boundary",
                "wikidata": "Q9928",
                "wikipedia": "nl:Heemstede (Noord-Holland)"
              },

    Coordinates: [[[x,y], [a,b]]]
    """

    log.debug("Trying to store a new organization")

    # Prefer the official_name, as it usually looks nicer.
    attempted_properties = ["name", "official_name", "alt_name", "localname"]
    name = ""
    for attempted_property in attempted_properties:
        if not name:
            name = properties[attempted_property]

    if not name:
        log.debug("Organization has no known name property, skipping.")
        return

    # A check on country code is performed to make sure no 'outside of country' websites are loaded and connected
    # to an organization.
    if "wikidata" in properties:
        iso3316_2_country_code = get_property_from_code(properties['wikidata'], ISO3316_2_COUNTRY_CODE)

        # some regions are marked by their subdivision code. This is LU-... The first two letters are the country code.
        if not iso3316_2_country_code:
            iso3316_2_country_code = get_property_from_code(properties['wikidata'], ISO3316_2_COUNTY_SUBDIVISION_CODE)
            if iso3316_2_country_code:
                iso3316_2_country_code = iso3316_2_country_code[0:2]

        if iso3316_2_country_code and country.upper() != iso3316_2_country_code.upper():
            log.debug(f"According to wikidata the imported region is not in {country} but in {iso3316_2_country_code}.")
            log.debug('Going to save the region under the new country. You probably got too much data back from OSM')
            country = iso3316_2_country_code.upper()

    # Verify that this doesn't exist yet to prevent double imports (when mistakes are made).
    if Organization.objects.all().filter(name=name,
                                         country=country,
                                         type__name=organization_type,
                                         is_dead=False).exists():
        log.debug(f"Organization {name} exists in country {country} and type {organization_type}, skipping.")
        return

    new_organization = Organization(
        name=name,
        type=OrganizationType.objects.all().filter(name=organization_type).first(),
        country=country,
        created_on=when if when else datetime.now(pytz.utc),
        wikidata=properties["wikidata"] if "wikidata" in properties else "",
        wikipedia=properties["wikipedia"] if "wikipedia" in properties else "",
    )
    new_organization.save()  # has to be done in a separate call. can't append .save() to the organization object.
    log.info(f"Saved new organization: {new_organization}")

    new_coordinate = Coordinate(
        created_on=when if when else datetime.now(pytz.utc),
        organization=new_organization,
        creation_metadata="Automated import via OSM.",
        geojsontype=coordinates["type"],  # polygon or multipolygon
        area=coordinates["coordinates"]
    )
    new_coordinate.save()
    log.info(f"Saved new coordinate: {new_coordinate}")

    # try to find official urls for this organization, as it's empty now. All those will then be onboarded and scanned.
    if "wikidata" in properties:
        add_official_websites(new_organization, properties["wikidata"])


def store_updates(feature: Dict, country: str = "NL", organization_type: str = "municipality", when=None):
    properties = feature["properties"]
    coordinates = feature["geometry"]

    """
    Handles the storing / administration of coordinates in failmap using the stacking pattern.

    "properties": {
                "@id": "relation/47394",
                "admin_level": "8",
                "authoritative": "yes",
                "boundary": "administrative",
                "name": "Heemstede",
                "ref:gemeentecode": "397",
                "source": "dataportal",
                "type": "boundary",
                "wikidata": "Q9928",
                "wikipedia": "nl:Heemstede (Noord-Holland)"
              },

    Coordinates: [[[x,y], [a,b]]]
    """
    # check if organization is part of the database
    # first try using it's OSM name
    matching_organization = match_organization(properties, country, organization_type)

    if not matching_organization:
        return

    add_official_websites(matching_organization, properties["wikidata"])

    if not when:
        old_coordinate = Coordinate.objects.filter(organization=matching_organization, is_dead=False)
    else:
        old_coordinate = Coordinate.objects.filter(organization=matching_organization, is_dead=False,
                                                   created_on__lte=when)

    if old_coordinate.count() == 1 and old_coordinate[0].area == coordinates["coordinates"]:
        log.info("Retrieved coordinates are the same, not changing anything.")
        return

    message = ""

    if old_coordinate.count() > 1:
        message = "Automated import does not support multiple coordinates per organization. " \
                  "New coordinates will be created."

    if old_coordinate.count() == 1:
        message = "New data received in automated import."

        log.info(message)

    for old_coord in old_coordinate:
        old_coord.is_dead = True
        old_coord.is_dead_since = when if when else datetime.now(pytz.utc)
        old_coord.is_dead_reason = message
        old_coord.save()

    # Update the wikipedia references, given we have them now.
    if "wikidata" in coordinates or "wikipedia" in coordinates:
        matching_organization.wikidata = properties["wikidata"] if "wikidata" in properties else "",
        matching_organization.wikipedia = properties["wikipedia"] if "wikipedia" in properties else "",
        matching_organization.save()

    Coordinate(
        created_on=when if when else datetime.now(pytz.utc),
        organization=matching_organization,
        creation_metadata="Automated import via OSM.",
        geojsontype=coordinates["type"],  # polygon or multipolygon
        area=coordinates["coordinates"],
    ).save()

    log.info("Stored new coordinates!")


def match_organization(openstreetmap_properties, country, organization_type):

    # in preferred order:
    attempted_properties = ["name", "official_name", "alt_name", "localname"]

    for attempted_property in attempted_properties:

        # By FAR not the same properties are used, sometimes not at all, sometimes all are used.
        if attempted_property not in openstreetmap_properties:
            continue

        # And if it's used, well, let's see if we can make a match...
        try:
            matching_organization = Organization.objects.filter(
                name=openstreetmap_properties[attempted_property],
                country=country,
                type__name=organization_type,
                is_dead=False).first()

            if matching_organization:
                return matching_organization

        except Organization.DoesNotExist:
            log.debug("Could not find organization by property 'name', trying another way.")

    log.info(f"""
    Organization from OSM is currently not found in the database.

    This happens when neighbouring countries are also returned from your OSM query. Or when you decided to remove
    some stuff from the map due to limitations of displaying that information. For example the Netherlands doesn't
    show the Antilles, as that would disproportionally show the map.

    You can import the region if you would like to have this information in your system. It will also import everything
    else currently.""")

    return None


def add_official_websites(organization, wikidata_code):

    website = get_property_from_code(wikidata_code, OFFICIAL_WEBSITE)

    if website:
        # they don't need to resolve
        extract = tldextract.extract(website)
        if extract.subdomain:
            organization.add_url(f"{extract.subdomain}.{extract.domain}.{extract.suffix}")
        organization.add_url(f"{extract.domain}.{extract.suffix}")
        log.debug(f"Added URL {website}. If it contained 'www', also without 'www'.")


def get_data_from_wambachers_zipfile(filename):
    # todo: this is VERY ugly code...
    zip = zipfile.ZipFile(filename)
    files = zip.namelist()
    f = zip.open(files[0], 'r')
    contents = f.read()
    f.close()
    data = json.loads(contents)
    return data


def get_osm_data_wambachers(country: str = "NL", organization_type: str = "municipality"):
    """
    When the config.WAMBACHERS_OSM_CLIKEY is configured, this routine will get the map data.

    It's the same as OSM, but with major seas and lakes cut out. That makes a nicer terrain on the website.
    # uses https://wambachers-osm.website/boundaries/ to download map data. Might not be the most updated, but it has
    # a more complete and better set of queries. For example; it DOES get northern ireland and it clips out the sea,
    # which makes it very nice to look at.
    # yes, i've donated, and so should you :)

    :param country:
    :param organization_type:
    :return:
    """

    """
    curl -f -o NL_province.zip 'https://wambachers-osm.website/boundaries/exportBoundaries
    ?cliVersion=1.0
    &cliKey=[key]  done: add cliKey to config
    &exportFormat=json
    &exportLayout=levels
    &exportAreas=land
    &union=false
    &from_al=4
    &to_al=4        done: get the right number
    &selected=NLD'  done: get 3 letter ISO code

    :param country:
    :param organization_type:
    :return:
    """

    # see if we cached a result
    filename = create_evil_filename([country, organization_type, str(timezone.now().date())], 'zip')
    filename = settings.TOOLS['openstreetmap']['output_dir'] + filename

    log.debug(f"Saving data to {filename}")

    # if the file has been downloaded recently, don't do that again.
    four_hours_ago = time.time() - 14400
    if os.path.isfile(filename) and four_hours_ago < os.path.getmtime(filename):
        log.debug("Already downloaded a coordinate file in the past four hours. Using that one.")
        # unzip the file and return it's geojson contents.
        return get_data_from_wambachers_zipfile(filename)

    level = get_region(country, organization_type)
    country = countries.get(country)
    country_3_char_isocode = country.alpha3
    if not level:
        raise NotImplementedError(
            "Combination of country and organization_type does not have a matching OSM query implemented.")

    url = f"https://wambachers-osm.website/boundaries/exportBoundaries" \
        f"?cliVersion=1.0" \
        f"&cliKey={config.WAMBACHERS_OSM_CLIKEY}" \
        f"&exportFormat=json" \
        f"&exportLayout=levels" \
        f"&exportAreas=land" \
        f"&union=false" \
        f"&from_al={level}" \
        f"&to_al={level}" \
        f"&selected={country_3_char_isocode}"

    # get's a zip file and extract the content. The contents is the result.
    response = requests.get(url, stream=True, timeout=(1200, 1200))
    response.raise_for_status()

    # show a nice progress bar when downloading
    with open(filename, 'wb') as f:
        i = 0
        for block in response.iter_content(chunk_size=1024):
            i += 1
            print_progress_bar(i, 100000, 'Wambacher OSM data')
            if block:
                f.write(block)
                f.flush()

    # unzip the file and return it's geojson contents.
    return get_data_from_wambachers_zipfile(filename)


def create_evil_filename(properties: List, extension: str):
    # remove everything, except a-zA-Z0-9 (? does it?)
    properties = [re.sub(r'\W+', '', property) for property in properties]

    return "_".join(properties) + "." + extension


def get_osm_data(country: str = "NL", organization_type: str = "municipality"):
    """
    Runs an overpass query that results in a set with administrative borders and points with metadata.

    :return: dictionary
    """

    filename = create_evil_filename([country, organization_type, str(timezone.now().date())], 'osm')
    filename = settings.TOOLS['openstreetmap']['output_dir'] + filename

    # if the file has been downloaded recently, don't do that again.
    four_hours_ago = time.time() - 14400
    if os.path.isfile(filename + ".polygons") and four_hours_ago < os.path.getmtime(filename):
        log.debug("Already downloaded a coordinate file in the past four hours. Using that one.")
        log.debug(filename + ".polygons")
        return json.load(open(filename + ".polygons"))

    """
        The overpass query interface can be found here: https://overpass-turbo.eu/
        More on overpass can be found here: https://wiki.openstreetmap.org/wiki/Overpass_API
        The OSM file needs to be converted to paths etc.

        How administrative boundaries work, with a list of admin levels:
        https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative
    """

    admin_level = get_region(country, organization_type)

    if not admin_level:
        raise NotImplementedError(
            "Combination of country and organization_type does not have a matching OSM query implemented.")

    # we used to use the country name, which doesn't work very consistently and requires a greater source of knowledge
    # luckily OSM supports ISO3166-2, just like django countries. So that's a perfect fit.
    query = f"""area["ISO3166-2"~"^{country}"]->.gem; relation(area.gem)[type=boundary]
            [boundary=administrative][admin_level={admin_level}]; out geom;"""

    log.info("Connecting to overpass to download data. Downloading can take a while (minutes)!")
    log.debug(query)
    response = requests.post("http://www.overpass-api.de/api/interpreter",
                             data={"data": query, "submit": "Query"},
                             stream=True,
                             timeout=(1200, 1200))

    response.raise_for_status()

    with open(filename, 'wb') as f:
        # total_length = int(response.headers.get('content-length'))
        # we don't get a content length from the api. So, "just" do something to show some progress...
        # {'Date': 'Tue, 20 Mar 2018 09:58:11 GMT', 'Server': 'Apache/2.4.18 (Ubuntu)', 'Vary': 'Accept-Encoding',
        # 'Content-Encoding': 'gzip', 'Keep-Alive': 'timeout=5, max=100', 'Connection': 'Keep-Alive',
        # 'Transfer-Encoding': 'chunked', 'Content-Type': 'application/osm3s+xml'}
        # overpass turbo does know this, probably _after_ downloading.
        # Assume 100 megabyte, NL = 40 MB. So give or take...
        i = 0
        for block in response.iter_content(chunk_size=1024):
            i += 1
            print_progress_bar(i, 100000, ' Generic OSM data')
            if block:
                f.write(block)
                f.flush()

    return osm_to_geojson(filename)


def osm_to_geojson(filename):
    log.info("Converting OSM file to polygons. This also can take a while...")
    try:
        with open(filename + ".polygons", "w") as outfile:
            subprocess.call(["osmtogeojson", filename], stdout=outfile)
    except subprocess.CalledProcessError:
        log.exception("Error while converting to polygons.")
    except OSError:
        log.exception("osmtogeojson tool not found.")

    return json.load(open(filename + ".polygons"))


def osmtogeojson_available():
    # todo: this check should be performed on startup?
    try:
        # todo: node --max_old_space_size=4000, for larger imprts... we don't even call node... :(
        subprocess.check_output(["osmtogeojson", "tesfile.osm"], stderr=subprocess.STDOUT, )
    except CalledProcessError as e:
        if "no such file or directory, open 'tesfile.osm'" in str(e.output):
            return True
        else:
            return False
    except FileNotFoundError:
        return False
