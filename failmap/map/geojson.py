import json
import logging
import subprocess
from datetime import datetime
from subprocess import CalledProcessError
from typing import Dict

import pytz
import requests
from django.conf import settings
from django.db import transaction
from rdp import rdp

from failmap.organizations.models import Coordinate, Organization

from ..celery import app

log = logging.getLogger(__package__)


# Updates in dataset before doing this in 2018:
# s-Hertogenbosch -> 's-Hertogenbosch
# Bergen (Noord-Holland) -> Bergen (NH)
# Bergen (Limburg) -> Bergen

# the map should look seamless when you're looking at the entire country, region etc. If it doesn't, increase
# the resolution.
resampling_resolutions = {
    'NL': {'municipality': 0.001}
}


def osmtogeojson_available():
    try:
        subprocess.check_output(["osmtogeojson", "tesfile.osm"], stderr=subprocess.STDOUT, )
    except CalledProcessError as e:
        if "no such file or directory, open 'tesfile.osm'" in str(e.output):
            return True
        else:
            return False
    except FileNotFoundError:
        return False


def update_coordinates(country: str = "NL", organization_type: str="municipality", when=None):

    if not osmtogeojson_available():
        raise FileNotFoundError("osmtogeojson was not found. Please install it and make sure python can access it. "
                                "Cannot continue.")

    log.info("Attempting to update coordinates for: %s %s " % (country, organization_type))
    update_coordinates_task(country, organization_type, when)


@app.task
@transaction.atomic
def update_coordinates_task(country: str = "NL", organization_type: str="municipality", when=None):

    # you are about to load 50 megabyte of data. Or MORE! :)
    data = get_osm_data(country, organization_type)

    log.info("Received coordinate data. Starting with: %s" % json.dumps(data)[0:200])

    log.info("Parsing features:")
    for feature in data["features"]:

        if "properties" not in feature:
            log.debug("Feature misses 'properties' property :)")
            continue

        if "name" not in feature["properties"]:
            log.debug("This feature does not contain a name: it might be metadata or something else.")
            continue

        # slower, but in a task. Still atomic this way.
        resolution = resampling_resolutions.get(country, {}).get(organization_type, 0.001)
        store_updates(resample(feature, resolution), country, organization_type, when)

    log.info("Resampling and update tasks have been created.")


def resample(feature: Dict, resampling_resolution: float=0.001):
    # downsample the coordinates using the rdp algorithm, mainly to reduce 50 megabyte to a about 150 kilobytes.
    # The code is a little bit dirty, using these counters. If you can refactor, please do :)

    log.info("Resampling path for %s" % feature["properties"]["name"])

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


def store_updates(feature: Dict, country: str="NL", organization_type: str="municipality", when=None):
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
    matching_organization = None
    try:
        matching_organization = Organization.objects.get(name=properties["name"],
                                                         country=country,
                                                         type__name=organization_type,
                                                         is_dead=False)
    except Organization.DoesNotExist:
        log.debug("Could not find organization by property 'name', trying another way.")

    if not matching_organization and "official_name" in properties:
        try:
            matching_organization = Organization.objects.get(name=properties["official_name"],
                                                             country=country,
                                                             type__name=organization_type,
                                                             is_dead=False)
        except Organization.DoesNotExist:
            log.debug("Could not find organization by property 'official_name', trying another way.")

    if not matching_organization and "alt_name" in properties:
        try:
            matching_organization = Organization.objects.get(name=properties["alt_name"],
                                                             country=country,
                                                             type__name=organization_type,
                                                             is_dead=False)
        except Organization.DoesNotExist:
            # out of options...
            # This happens sometimes, as you might get areas that are outside the country or not on the map yet.
            log.debug("Could not find organization by property 'alt_name', we're out of options.")
            log.info("Organization from OSM does not exist in failmap, create it using the admin interface: '%s' "
                     "This might happen with neighboring countries (and the antilles for the Netherlands) or new "
                     "regions."
                     "If you are missing regions: did you create them in the admin interface or with an organization "
                     "merge script? Developers might experience this error using testdata etc.", properties["name"])
            log.info(properties)

    if not matching_organization:
        log.info("No matching organization found, no name, official_name or alt_name matches.")
        return

    # check if we're dealing with the right Feature:
    if country == "NL" and organization_type == "municipality":
        if properties.get("boundary", "-") != "administrative":
            log.info("Feature did not contain properties matching this type of organization.")
            log.info("Missing boundary:administrative")
            return

    # todo: dutch stuff can be handled via gemeentecodes.

    # Check if the current coordinates are the same, if so, don't do anything.
    # It is possible that an organization has multiple coordinates. Since we always get a single multipoly back,
    # we'll then just overwrite all of them to the single one.

    old_coordinate = Coordinate.objects.filter(organization=matching_organization, is_dead=False)

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

    Coordinate(
        created_on=when if when else datetime.now(pytz.utc),
        organization=matching_organization,
        creation_metadata="Automated import via OSM.",
        geojsontype=coordinates["type"],  # polygon or multipolygon
        area=coordinates["coordinates"],
    ).save()

    log.info("Stored new coordinates!")


def get_osm_data(country: str= "NL", organization_type: str= "municipality"):
    """
    Runs an overpass query that results in a set with administrative borders and points with metadata.

    Test data: # "/Applications/XAMPP/xamppfiles/htdocs/failmap/admin/failmap/map/map_updates/Netherlands.geojson"

    :return: dictionary
    """

    # could be tempfile.mkdtemp() -> no, that makes debugging harder.
    # currently saving the download files for debugging and inspection.
    filename = "%s_%s_%s.osm" % (country, organization_type, datetime.now(pytz.utc).date())
    filename = settings.TOOLS['openstreetmap']['output_dir'] + filename

    # to test this, without connecting to a server but handle the data returned today(!)
    download_and_convert = True

    if country == "NL" and organization_type == "municipality":

        # shorthand for debugging.
        if not download_and_convert:
            return json.load(open(filename + ".geojson"))

        # returns an OSM file, you need to convert this
        # while JSON is nearly instant, a large text file with even less data takes way more time.
        # https handshake error at time of release, downgrading to http... :')
        log.info("Connecting to overpass to download data. Downloading can take a while!")
        response = requests.post("http://www.overpass-api.de/api/interpreter",
                                 data={"data": 'area[name="Nederland"]->.gem; '
                                       'relation(area.gem)["type"="boundary"][admin_level=8]; '
                                       'out geom;',
                                       "submit": "Query"},
                                 stream=True,
                                 timeout=(600, 600))
        # 30 seconds to connect? nope, is somethign else, 10 minutes to retrieve the data.)

        response.raise_for_status()

        log.info("Writing received data to file.")
        with open(filename, 'wb') as handle:
            for block in response.iter_content(1024):
                handle.write(block)

        # convert the file:
        log.info("Converting OSM to geojson")

        try:
            # shell is True can only be somewhat safe if all input is not susceptible to manipulation
            # in this case the filename and all related info is verified.
            # todo: where are the requirements this command is available?
            # todo: why write to an intermediate file using shell redirects when you can just take
            # the output from the command directly?
            # this can lead to double memory usage, so therefore it might not be really helpful.
            subprocess.check_call("osmtogeojson %s > %s" % (filename, filename + ".geojson"), shell=True)
        except subprocess.CalledProcessError:
            log.exception("Error while converting to geojson.")
        except OSError:
            log.exception("osmtogeojson tool not found.")

        return json.load(open(filename + ".geojson"))

    raise NotImplemented("Combination of country and organization_type does not have a matching OSM query implemented.")
