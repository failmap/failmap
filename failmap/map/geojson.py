import json
import logging
import subprocess
from datetime import datetime
from typing import Dict

import pytz
import requests
from django.db import transaction

from failmap.organizations.models import Coordinate, Organization
from rdp import rdp

from ..celery import app

log = logging.getLogger(__package__)


@transaction.atomic
def update_coordinates(country: str = "NL", organization_type: str="municipality"):

    log.info("Attempting to update coordinates for: %s %s " % (country, organization_type))

    # you are about to load 50 megabyte of data. Or MORE! :)
    data = get_osm_data(country, organization_type)

    import json
    log.info("Recieved coordinate data. Starting with: %s" % json.dumps(data)[0:200])

    resampling_resolution = get_sampling_resolution(country, organization_type)

    for feature in data["features"]:

        if not "properties" in feature.keys():
            log.debug("Feature misses property")
            continue

        if not "name" in feature["properties"].keys():
            log.debug("Feature does not contain a name, cannot relate feature to existing data.")
            continue

        log.info("Resampling path for %s" % feature["properties"]["name"])

        task = (resample.s(feature, resampling_resolution) | store_updates.s(country, organization_type))
        task.apply_async()

        # feature = resample_data(feature, resampling_resolution)
        # store_coordinates(feature, country, organization_type)


@app.task
def resample(feature: Dict, resampling_resolution: float=0.001):
    # downsample the coordinates using the rdp algorithm, mainly to reduce 50 megabyte to a about 150 kilobytes.
    # The code is a little bit dirty, using these counters. If you can refactor, please do :)
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

            # feature["geometry"]["coordinates"][i] = rdp(coordinate, epsilon=resampling_resolution)
            j = 0
            i += 1

    return feature


def get_sampling_resolution(country: str="NL", organization_type: str="municipality") -> float:

    if country == "NL" and organization_type == "municipality":
        return 0.0001

    return 0.0001


@app.task
def store_updates(feature: Dict, country: str="NL", organization_type: str="municipality"):
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
    try:
        matching_organization = Organization.objects.get(name=properties["name"],
                                                         country=country,
                                                         type__name=organization_type,
                                                         is_dead=False)
    except Organization.DoesNotExist:
        log.info("Organization from OSM does not exist in failmap, create it using the admin interface: '%s'" %
                 properties["name"])
        log.info("This might happen with neighboring countries (and the antilles for the Netherlands).")
        log.info("Developers might experience this error using testdata etc.")
        log.info(properties)
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
        message = "New data received in automated import. DEAL WITH IT!"

        log.info(message)

    for old_coord in old_coordinate:
        old_coord.is_dead = True
        old_coord.is_dead_since = datetime.now(pytz.utc)
        old_coord.is_dead_reason = message
        old_coord.save()

    new_coordinate = Coordinate()
    new_coordinate.created_on = datetime.now(pytz.utc)
    new_coordinate.organization = matching_organization
    new_coordinate.creation_metadata = "Automated import via OSM."
    new_coordinate.geojsontype = coordinates["type"]  # polygon or multipolygon
    new_coordinate.area = coordinates["coordinates"]
    new_coordinate.save()

    log.info("Stored new coordinates!")


# todo: storage dir for downloaded file (can be temp)
def get_osm_data(country: str= "NL", organization_type: str= "municipality"):
    """
    Runs an overpass query that results in a set with administrative borders and points with metadata.

    Test data: # "/Applications/XAMPP/xamppfiles/htdocs/failmap/admin/failmap/map/map_updates/Netherlands.geojson"

    :return: dictionary
    """

    filename = "%s_%s_%s.osm" % (country, organization_type, datetime.now().date())

    # to test this, without connecting to a server but handle the data returned today(!)
    download_and_convert = False

    if country == "NL" and organization_type == "municipality":

        if download_and_convert:
            # returns an OSM file, you need to convert this
            # while JSON is nearly instant, a large text file with even less data takes way more time.
            response = requests.post("https://www.overpass-api.de/api/interpreter",
                                     data={"data": 'area[name="Nederland"]->.gem; '
                                           'relation(area.gem)["type"="boundary"][admin_level=8]; '
                                           'out geom;',
                                           "submit": "Query"}, stream=True)

            log.info("Writing recieved data to file.")
            with open(filename, 'wb') as handle:
                for block in response.iter_content(1024):
                    handle.write(block)

            # convert the file:
            log.info("Converting OSM to geojson")

            try:
                # shell is True can only be somewhat safe if all input is not susceptible to manipulation
                # in this case the filename and all related info is verified.
                subprocess.check_call("osmtogeojson %s > %s" % (filename, filename + ".geojson"), shell=True)
            except subprocess.CalledProcessError:
                log.info("Error while converting to geojson.")
            except OSError:
                log.info("osmtogeojson not found.")

        return json.load(open(filename + ".geojson"))

    raise NotImplemented("Combination of country and organization_type does not have a matching OSM query implemented.")
