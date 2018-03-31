import json
import logging
import os.path
import subprocess
import time
from datetime import datetime
from subprocess import CalledProcessError
from typing import Dict, List
from urllib.error import HTTPError

import pytz
import requests
import tldextract
from clint.textui import progress
from django.conf import settings
from django.db import transaction
from rdp import rdp
from wikidata.client import Client

from failmap.organizations.models import Coordinate, Organization, OrganizationType, Url

log = logging.getLogger(__package__)


# the map should look seamless when you're looking at the entire country, region etc. If it doesn't, increase
# the resolution.
resampling_resolutions = {
    'NL': {'municipality': 0.001}
}

queries = {
    "NL": {
        # 4: province, 5: water board, 8: municipality, 9: stadsdelen, 10: settlements, 11: neighborhoods (wijken)
        "municipality":
            'area[name="Nederland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
        # empty :(
        "water board":
            'area[name="Nederland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=5]; out geom;',
        "province":
            'area[name="Nederland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=4]; out geom;',
    },
    "SE": {
        # 3: "landsdeel", 7: municipality,  8: district, 4: province,
        "municipality":
            'area[name="Sverige"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
        "province":
            'area[name="Sverige"]->.gem; relation(area.gem)["type"="boundary"][admin_level=4]; out geom;',
    },
    "DE": {
        # Don't even try to translate (or understand) German regions. Just take it as it is, name it like they do.
        # https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative
        # Here is a nice image to help you: https://en.wikipedia.org/wiki/Districts_of_Germany
        "bundesland":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=4]; out geom;',
        "regierungsbezirk":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=5]; out geom;',
        "landkreis_kreis_kreisfreie_stadt":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
        "samtgemeinde_verwaltungsgemeinschaft":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
        # huge!
        """
        A bit too huge?
        FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory
         1: node::Abort() [/usr/local/bin/node]
         2: node::FatalException(v8::Isolate*, v8::Local<v8::Value>, v8::Local<v8::Message>) [/usr/local/bin/node]
         3: v8::Utils::ReportOOMFailure(char const*, bool) [/usr/local/bin/node]
         4: v8::internal::V8::FatalProcessOutOfMemory(char const*, bool) [/usr/local/bin/node]
         5: v8::internal::Factory::NewFillerObject(int, bool, v8::internal::AllocationSpace) [/usr/local/bin/node]
         6: v8::internal::Runtime_AllocateInTargetSpace(int, v8::internal::Object**, v8::internal::Isolate*)
         [/usr/local/bin/node]
         7: 0x2fb7fb8ed46
         8: 0x2fb7fcf4e76
         9: 0x2fb7fcdd264
        10: 0x2fb7fb85cd5
        """
        "stadt_gemeinde":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
        "stadtbezirk_gemeindeteil_mit_selbstverwaltung":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=9]; out geom;',
        "stadtteil_gemeindeteil_ohne_selbstverwaltung":
            'area[name="Deutschland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=10]; out geom;',
    },
    "FR": {
        # Communes
        # Use name=* to indicate the name of the commune, and
        # ref:INSEE=* to indicate the unique identifier given by INSEE (COG).
        "municipality":
            'area[name="France"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
    },
    "NO": {
        # Muncipiality (Kommue) (430) Example: Stavanger, Sandnes etc
        "municipality":
            'area[name="Norge"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
    },
    "FI": {
        # Kunnat / Kaupungit, LAU 2, for ref=*, see Väestörekisterikeskus, kuntaluettelo): Helsinki
        # municipality
        "municipality":
            'area[name="Suomi"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
    },
    "UK": {
        # parishes / communities, probably not a municipality?
        "municipality":
            'area[name="United Kingdom"]->.gem; relation(area.gem)["type"="boundary"][admin_level=10]; out geom;',
    },
    "BE": {
        # Municipalities
        "municipality":
            'area[name="België"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
    },
    "ES": {
        "municipality":
            'area[name="España"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
        "province":
            'area[name="España"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
    },
    "PT": {
        "municipality":
            'area[name="Portugal"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
    },
    "LU": {
        "municipality":
            'area[name="Luxembourg"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
    },
    "DK": {
        "municipality":
            'area[name="Danmark"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
    },
    "CH": {
        "municipality":
            'area[name="Schweiz/Suisse/Svizzera/Svizra"]->.gem; '
            'relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
    },
    "AT": {
        "municipality":
            'area[name="Österreich"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
    },
    "IT": {
        "municipality":
            'area[name="Italia"]->.gem; relation(area.gem)["type"="boundary"][admin_level=8]; out geom;',
        "province":
            'area[name="Italia"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
    },
    "IE": {
        "municipality":
            'area[name="Ireland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=7]; out geom;',
        "county":
            'area[name="Ireland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
        "province":
            'area[name="Ireland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=5]; out geom;',
    },
    "IS": {
        "municipality":
            'area[name="Iceland"]->.gem; relation(area.gem)["type"="boundary"][admin_level=6]; out geom;',
    },
}


@transaction.atomic
def import_from_scratch(countries: List[str]=None, organization_types: List[str]=None, when=None):
    """
    Run this when you have nothing on the organization type in that country. It will help bootstrapping a
    certain region.

    :param countries: uppercase list of 2-letter country codes.
    :param organization_types: the types you want to import.
    :param when:
    :return:
    """

    log.info("Countries: %s" % countries)
    log.info("Region(s): %s" % organization_types)

    if not countries or countries == [None]:
        countries = ["NL"]

    # paramter hate causes organization_types == [None]
    if not organization_types or organization_types == [None]:
        log.info("Going to get all existing organization types, and try to import them all.")
        organization_types = list(OrganizationType.objects.all().values_list('name', flat=True))

    for country in countries:
        for organization_type in organization_types:

            if not queries.get(country, {}).get(organization_type, None):
                log.info("The combination of %s and %s does not exist in OSM. Skipping." % (country, organization_type))
                continue

            data = get_osm_data(country, organization_type)
            for feature in data["features"]:

                if "properties" not in feature:
                    continue

                if "name" not in feature["properties"]:
                    continue

                resolution = resampling_resolutions.get(country, {}).get(organization_type, 0.001)
                store_new(resample(feature, resolution), country, organization_type, when)

                # can't do multiprocessing.pool, given non global functions.

    log.info("Import finished.")


@transaction.atomic
def update_coordinates(country: str = "NL", organization_type: str="municipality", when=None):

    if not osmtogeojson_available():
        raise FileNotFoundError("osmtogeojson was not found. Please install it and make sure python can access it. "
                                "Cannot continue.")

    log.info("Attempting to update coordinates for: %s %s " % (country, organization_type))

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


def store_new(feature: Dict, country: str="NL", organization_type: str="municipality", when=None):
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

    log.debug(properties)

    # Verify that this doesn't exist yet to prevent double imports (when mistakes are made).
    if Organization.objects.all().filter(name=properties["name"],
                                         country=country,
                                         type__name=organization_type,
                                         is_dead=False).exists():
        return

    if "official_name" in properties:
        if Organization.objects.all().filter(name=properties["official_name"],
                                             country=country,
                                             type__name=organization_type,
                                             is_dead=False).exists():
            return

    # Prefer the official_name, as it usually looks nicer.
    name = properties["official_name"] if "official_name" in properties else properties["name"]

    new_organization = Organization(
        name=name,
        type=OrganizationType.objects.all().get(name=organization_type),
        country=country,
        created_on=when if when else datetime.now(pytz.utc),
        wikidata=properties["wikidata"] if "wikidata" in properties else "",
        wikipedia=properties["wikipedia"] if "wikipedia" in properties else "",
    )
    new_organization.save()  # has to be done in a separate call. can't append .save() to the organization object.
    log.info("Saved new organization: %s" % new_organization)

    new_coordinate = Coordinate(
        created_on=when if when else datetime.now(pytz.utc),
        organization=new_organization,
        creation_metadata="Automated import via OSM.",
        geojsontype=coordinates["type"],  # polygon or multipolygon
        area=coordinates["coordinates"]
    )
    new_coordinate.save()
    log.info("Saved new coordinate: %s" % new_coordinate)

    # try to find official urls for this organization, as it's empty now. All those will then be onboarded and scanned.
    if "wikidata" in properties:

        # validate that this region belongs to the right country
        # country = country, P17, you'll get a Q back
        # From the country get P297: ISO 3166-1 alpha-2 code
        country = ""
        isocode = ""

        website = ""
        try:
            client = Client()  # Q9928
            entity = client.get(properties["wikidata"], load=True)
            website = str(entity.get(client.get("P856"), None))  # P856 == Official Website.
            country = entity.get(client.get("P17"), None)
        except HTTPError as e:
            # No entity with ID Q15111448 was found... etc.
            # perfectly possible. In that case, no website, and thus continue.
            pass
        except Exception as e:
            # don't cause problems here... if the service is down, bad luck, try an import later etc...
            pass

        log.debug("Country: %s" % country)
        # validate country:
        if country:
            try:
                client = Client()  # Q9928
                entity = client.get(country.id, load=True)
                isocode = str(entity.get(client.get("P297"), None))
                log.debug("Retrieved ISO code: %s" % isocode)
            except HTTPError as e:
                # No entity with ID Q15111448 was found... etc.
                # perfectly possible. In that case, no website, and thus continue.
                pass
            except Exception as e:
                # don't cause problems here... if the service is down, bad luck, try an import later etc...
                pass

        log.debug("Matching isocode: %s", isocode)

        # instead of removing or breaking things, just update the organization to belong to this country.
        if isocode and new_organization.country != isocode.upper():
            log.info("The imported organization is from another country, saving it as such. This may cause some "
                     "issues as double organizations can be created.")
            new_organization.country = isocode.upper()
            new_organization.save()

        if not website or website == "None":
            return

        extract = tldextract.extract(website)

        if extract.subdomain:
            url = Url(url="%s.%s.%s" % (extract.subdomain, extract.domain, extract.suffix))
            url.save()
            url.organization.add(new_organization)
            url.save()
            log.info("Also found a subdomain website for this organization: %s" % website)

        # Even if it doesn't resolve directly, it is helpful for some scans:
        url = Url(url="%s.%s" % (extract.domain, extract.suffix))
        url.save()
        url.organization.add(new_organization)
        url.save()
        log.info("Also found a top level website for this organization: %s" % website)


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


def get_osm_data(country: str= "NL", organization_type: str= "municipality"):
    """
    Runs an overpass query that results in a set with administrative borders and points with metadata.

    :return: dictionary
    """

    filename = "%s_%s_%s.osm" % (country, organization_type, datetime.now(pytz.utc).date())
    filename = settings.TOOLS['openstreetmap']['output_dir'] + filename

    # if the file has been downloaded recently, don't do that again.
    four_hours_ago = time.time() - 14400
    if os.path.isfile(filename + ".geojson") and four_hours_ago < os.path.getmtime(filename):
        log.debug("Already downloaded a coordinate file in the past four hours. Using that one.")
        log.debug(filename + ".geojson")
        return json.load(open(filename + ".geojson"))

    """
        The overpass query interface can be found here: https://overpass-turbo.eu/

        More on overpass can be found here: https://wiki.openstreetmap.org/wiki/Overpass_API

        The OSM file needs to be converted to paths etc.

        How administrative boundaries work, with a list of admin levels:
        https://wiki.openstreetmap.org/wiki/Tag:boundary=administrative
    """

    query = queries.get(country, {}).get(organization_type, None)

    if not query:
        raise NotImplemented(
            "Combination of country and organization_type does not have a matching OSM query implemented.")

    log.info("Connecting to overpass to download data. Downloading can take a while (minutes)!")
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
        for block in progress.bar(response.iter_content(chunk_size=1024), expected_size=(10240000 / 1024) + 1):
            if block:
                f.write(block)
                f.flush()

    log.info("Converting OSM file to geojson. This also can take a while...")
    try:
        with open(filename + ".geojson", "w") as outfile:
            subprocess.call(["osmtogeojson", filename], stdout=outfile)
    except subprocess.CalledProcessError:
        log.exception("Error while converting to geojson.")
    except OSError:
        log.exception("osmtogeojson tool not found.")

    return json.load(open(filename + ".geojson"))


def osmtogeojson_available():
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
