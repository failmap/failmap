#!/usr/bin/python3
# Note: run make fix and make check before committing code.

"""
Scrapes organisations from Zorgkaart Nederland API
provides the task: vendor.tilanus.zorgkaart.scrape
uses websecmap config as parameters

organisations()
    Returns list of organsations in data structure
    as returned by zorgkaart Nederland. Applies
    filters as set in config.
    DANGER LOTS OF OUTPUT WHEN NOT FILTERED

organisation_types()
    Returns a list of organisation types as currently
    present in the zorgkaart Nederland database.

translate(organisation_list)
    Translates the Zorgkaart Nederland organisations list
    to a list that can be imprted into WebSecMap.

scrape()
    Retrieves list of organisations (applying filter in
    WebSecMap config) and translates and inserts/updates
    them into the database of WebSecMap.

create_task()
    Inserts a periodic task for running the scraper weekly
    into the WebSecMap configuration.
"""

import json
import sys
from time import sleep
from typing import List, Dict, Any

import googlemaps
import requests
import tldextract
import logging

from constance import config
from django.db import transaction
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from iso3166 import countries_by_alpha2
from requests.auth import HTTPBasicAuth

from websecmap.celery import app
from websecmap.organizations.models import Organization, OrganizationType, Coordinate, Url

log = logging.getLogger(__package__)


@transaction.atomic
def organization_and_url_import(flat_organizations: List[Dict[str, Any]]):

    if not config.GOOGLE_MAPS_API_KEY:
        log.warning("Warning: the google maps api key is not set, fallback geocoding of addresses will not happen.")

    """
    Imports a structure of organizations, coordinates and urls. Structure you need to send:

    [
        {
            # Representative name of the organization. For example: Nationaal Cyber Security Centrum (NCSC)
            # Organizations with long names are usually also abbreviated, add the abbreviation in parenthesis so
            # it can be found on the map.
            # If you want to show everything on a single map, add the layer to the name so it can be searched. (this
            # is a hack and it doesn't translate into multiple languages).
            # required, string, (updatable via surrogate ID)
            'name': 'Nationaal Cyber Security Centrum (NCSC)',

            # Optional: address of the organization, can be any string. Can be used for geocoding in websecmap.
            # optional, string, (updatable via surrogate ID)
            'address': 'optional, address',

            # ISO 3166-2 country code, such as NL, DE, FR, GB
            # required, ISO 3166-2 country code
            'country: 'NL',

            # What map layer the organization belongs to. Internally this is an organization_type.
            # Unfortunately the relation between organization and organzation_type = 1-1 at the moment.
            # A duplicate organization can be manages with a surrogate ID.
            # required, string
            'layer': '',

            # Can be Point, MultiPolygon or Polygon. A geojson type. See geojson.org
            # required, string, (updatable via surrogate ID)
            'coordinate_type': 'Point',

            # The geojson data that needs to be stored. See geojson.org for specification of this data.
            # The order of points is Lng, Lat, the example points to somewhere in amsterdam.
            # required, geojson, (updatable via surrogate ID)
            'coordinate_area': [4, 52],

            # Any ID that is used to identify this object in an external database. Use this ID to retrieve the
            # existing object and alter its name, address, coordinate_type and coordinates. All organizations
            # with the same ID are updated: except when the ID is empty.
            # Note that urls are not updated, as the url can be shared with many organizations
            # optional, string
            'surrogate_id': '',

            # websecmap_id, optional. Can be used to identify an object that needs to be updated as done with
            # surrogate id. Will be ignored if empty.
            # optional, string
            'id': '',

            # list of urls. Websecmap can discover subdomains if needed (which saves data). If that feature is
            # disabled make sure this list of domains is complete.
            # optional: List[str]
            'urls': ['example.com', 'myexample.com']
        },
        {
            ...
        },
    ]

    :return:
    """

    for flat_organization in flat_organizations:

        validate_flat_organization(flat_organization)

        # try to handle updates to existing organizations.
        # id is unique, only one organization has this id.
        if flat_organization.get("id", None):
            existing_organizations = Organization.objects.all().filter(id=flat_organization["id"]).first()
            if existing_organizations:
                update_flat_organization(flat_organization, existing_organizations=[existing_organizations])
                add_urls_to_organizations(organizations=existing_organizations, urls=flat_organization.get("urls", []))
                continue

        # multiple organizations can have the same surrogate_id
        if flat_organization.get("surrogate_id", None):
            existing_organizations = list(
                Organization.objects.all().filter(surrogate_id=flat_organization["surrogate_id"])
            )
            if existing_organizations:
                update_flat_organization(flat_organization, existing_organizations=existing_organizations)
                add_urls_to_organizations(organizations=existing_organizations, urls=flat_organization.get("urls", []))
                continue

        new_organization = add_flat_organization(flat_organization)
        add_urls_to_organizations(organizations=[new_organization], urls=flat_organization.get("urls", []))


_all_ = organization_and_url_import

# Periodic task name
TaskName = "zorgkaart import (hidden)"

# right now we there is a page limit of 1000 and max 123000 items
# so the the default limit of 1000 is OK but not future proof
# raise it for all security
sys.setrecursionlimit(10000)


def create_task():
    """Adds scraping task to celery jobs"""
    if not PeriodicTask.objects.filter(name=TaskName).first():
        p = PeriodicTask(
            **{
                "name": TaskName,
                "task": "websecmap.api.apis.zorgkaart.scrape",
                "crontab": CrontabSchedule.objects.get(id=7),
            }
        )
        p.save()
        log.info(f"Created Periodic Task for zorgkaart scraper with name: {TaskName}")


def do_request(url, params={}, previous_items=[]):
    """Internal function, performs API requests and merges paginated data"""
    # default to max limit of API
    if "limit" not in params.keys():
        params["limit"] = 10000
    # set page
    if "page" not in params.keys():
        params["page"] = 1
    log.debug(f"Zorgkaart scraper request with parameters: {params}")

    response = requests.get(
        url, auth=HTTPBasicAuth(config.ZORGKAART_USERNAME, config.ZORGKAART_PASSWORD), params=params
    )
    response.raise_for_status()
    result = response.json()
    # merge with results from reursions above
    items = previous_items + result["items"]
    # do we have everything
    if result["count"] > result["page"] * result["limit"]:
        # recursion because recursive programming is utterly uncomprehensible but fun
        params["page"] += 1
        log.debug(f"Zorgkaat scraper requesting nest page: {params['page']}")
        items = do_request(url, params, items)
    else:
        if not result["count"] == len(items):
            log.error(
                f"Zogkaart scraper: Zorgkaart reported {result['count']} records but we recieved {len(items)} records."
            )
    return items


def organisations():
    """
    Get a list of organisations as present in Zorgkaart

    returns:
        a list of dicts, datastructure as provided by Zorgkaart
    """
    params = json.loads(config.ZORGKAART_FILTER)
    if not type(params) == dict:
        log.error(f"Zorgkaat scrape: invalid filter ({params}), ignoring")
        params = {}
    log.debug(f"Zorgkaart scraper requesting organisations using filter: {params}")
    items = do_request(config.ZORGKAART_ENDPOINT, params)
    return items


def organisation_types():
    """
    get a list of organisation types present in Zorgkaart

    returns:
        a list of dicts with keys: 'id' (str) and 'name' (str)
    """
    url = "https://api.zorgkaartnederland.nl/api/v1/companies/types"
    items = do_request(url)
    return items


def translate(orglist):
    """
    translates a list of organisations as provided by Zorgkaart into a list of
    organisations that can be imported into WebSecMap.

    arguments:
        orglist - a list Zorgkaart-type list of organisations

    Returns:
        a list of dicts containing data that can be imported into WebSecMap.
    """

    outlist = []
    for org in orglist:

        if not OrganizationType.objects.all().filter(name=org["type"]).first():
            OrganizationType.objects.create(name=org["type"])

        outlist.append(
            {
                "name": org["name"] + " (" + org["type"] + ")",
                "layer": OrganizationType.objects.all().filter(name=org["type"]).first(),
                "country": "NL",
                "coordinate_type": "Point",
                "coordinate_area": [org["location"]["longitude"], org["location"]["latitude"]],
                "address": org["addresses"][0]["address"]
                + ", "
                + org["addresses"][0]["zipcode"]
                + " "
                + org["addresses"][0]["city"]
                + ", "
                + org["addresses"][0]["country"],
                "surrogate_id": org["name"] + "_" + org["type"] + "_" + org["id"],
                "urls": org["websites"],
            }
        )
    return outlist


@app.task(queue="storage")
def scrape():
    """
    Retrieves list of organisations (applying the filter in
    WebSecMap config) and translates and inserts/updates
    them into the database of WebSecMap.
    """
    orglist = organisations()
    wsmlist = translate(orglist)
    organization_and_url_import(wsmlist)
    log.info(f"Zorgkaart scrape updated organisations. Current organisation count: {len(orglist)}")
    return


def validate_flat_organization(flat_organization: Dict):
    layer = OrganizationType.objects.all().filter(name=flat_organization.get("layer", "")).first()
    if not layer:
        raise ValueError(
            f"Layer {flat_organization.get('layer', '')} " f"not defined. Is this layer defined in this installation?"
        )

    if flat_organization.get("country", "") not in countries_by_alpha2:
        raise ValueError("Country is required and needs to be an ISO3166-2 code.")

    if not flat_organization.get("name", None):
        raise ValueError("Added organization does not have a name, can not create organization.")

    if flat_organization.get("coordinate_type", None) not in ["Point", "MultiPolygon", "Polygon"]:
        raise ValueError(
            "Geojsontype not supported yet, or invalid geojson type. Valid are: " "['Point', 'MultiPolygon', 'Polygon']"
        )

    if flat_organization.get("id", None) and flat_organization.get("surrogate_id", None):
        raise ValueError(
            "When setting both the id and surrogate_id, it's not possible to determine what object"
            "needs changing. ID is unique, surrogate_id can be many. Choose an approach and try again."
        )


def add_flat_organization(flat_organization: Dict) -> Organization:
    o = Organization(
        **{
            "name": flat_organization["name"],
            "internal_notes": flat_organization.get("address", ""),
            "type": OrganizationType.objects.all().filter(name=flat_organization.get("layer", "")).first(),
            "country": flat_organization["country"],
            "surrogate_id": flat_organization["surrogate_id"],
        }
    )
    o.save()

    if flat_organization["coordinate_area"] == [0, 0] and flat_organization["coordinate_type"] == "Point":
        flat_organization["coordinate_area"] = retrieve_geocode(
            f"{flat_organization['name']}, {flat_organization.get('address', '')}"
        )

        # still no coordinate? then don't save one:
        if flat_organization["coordinate_area"] == [0, 0]:
            return o

    # add coordinate
    c = Coordinate(
        **{
            "geojsontype": flat_organization["coordinate_type"],
            "area": flat_organization["coordinate_area"],
            "organization": o,
        }
    )
    c.save()

    return o


def retrieve_geocode(string):
    # rate limit
    sleep(0.3)

    gmaps = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)
    geocode_result = gmaps.geocode(string)

    if geocode_result:
        return [geocode_result[0]["geometry"]["location"]["lng"], geocode_result[0]["geometry"]["location"]["lat"]]

    return [0, 0]


def update_flat_organization(flat_organization: Dict, existing_organizations: List[Organization]) -> None:
    # name, address, coordinate_type, coordinate can be updated.

    for existing_organization in existing_organizations:
        existing_organization.name = flat_organization["name"]
        existing_organization.internal_notes = flat_organization.get("address", existing_organization.internal_notes)
        existing_organization.save()

        existing_coordinate = Coordinate.objects.all().filter(organization=existing_organization).first()
        # try to upgrade coordinates that are now 0, 0 and are also given 0, 0
        if all(
            [
                existing_coordinate,
                flat_organization["coordinate_area"] == [0, 0],
                flat_organization["coordinate_type"] == "Point",
            ]
        ):
            flat_organization["coordinate_area"] = retrieve_geocode(
                f"{flat_organization['name']}, {flat_organization.get('address', '')}"
            )

        # and now update the coordinate that match this organization
        # and make sure that the coordinate is plotable.
        if flat_organization["coordinate_area"] != [0, 0]:
            cs = Coordinate.objects.all().filter(organization=existing_organization).first()
            cs.geojsontype = flat_organization["coordinate_type"]
            cs.area = flat_organization["coordinate_area"]
            cs.save()


def add_urls_to_organizations(organizations: List[Organization], urls: List[str]) -> None:
    for organization in organizations:
        for url in urls:
            # make the API easier to use:
            # will parse extensive urls: https://www.apple.com:80/yolo/swag
            extract = tldextract.extract(url)

            if extract.subdomain:
                url = f"{extract.subdomain}.{extract.domain}.{extract.suffix}"
                new_url = Url.add(url)
                new_url.organization.add(organization)

            if extract.domain:
                url = f"{extract.domain}.{extract.suffix}"
                new_url = Url.add(url)
                new_url.organization.add(organization)
