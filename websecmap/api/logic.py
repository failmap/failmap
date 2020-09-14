import csv
import logging
from datetime import datetime
from io import StringIO
from time import sleep
from typing import Any, Dict, List

import googlemaps
import pytz
import tldextract
from constance import config
from django.db import transaction
from django.db.models import Q
from iso3166 import countries_by_alpha2

from websecmap.api.models import SIDNUpload
from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url

log = logging.getLogger(__package__)


def get_map_configuration():
    # Using this, it's possible to get the right params for 2ndlevel domains

    configs = (
        Configuration.objects.all().filter(is_displayed=True, is_the_default_option=True).order_by("display_order")
    )

    data = []
    for map_config in configs:
        data.append({"country": map_config.country.code, "layer": map_config.organization_type.name})

    return data


def get_2ndlevel_domains(country, layer):
    urls = (
        Url.objects.all()
        .filter(
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            organization__country=get_country(country),
            organization__type=get_organization_type(layer),
        )
        .values_list("url", flat=True)
    )

    urls = list(set(urls))

    return urls


def get_uploads(user):
    # last 500 should be enough...
    uploads = SIDNUpload.objects.all().filter(by_user=user).defer("posted_data")[0:500]

    serialable_uploads = []
    for upload in uploads:
        serialable_uploads.append(
            {
                "when": upload.at_when.isoformat(),
                "state": upload.state,
                "amount_of_newly_added_domains": upload.amount_of_newly_added_domains,
                "newly_added_domains": upload.newly_added_domains,
            }
        )

    return list(serialable_uploads)


def get_uploads_with_results(user):
    uploads = (
        SIDNUpload.objects.all()
        .filter(by_user=user, amount_of_newly_added_domains__gt=0)
        .defer("posted_data")
        .order_by("-at_when")
    )

    serialable_uploads = []
    for upload in uploads:
        serialable_uploads.append(
            {
                "when": upload.at_when.isoformat(),
                "state": upload.state,
                "amount_of_newly_added_domains": upload.amount_of_newly_added_domains,
                "newly_added_domains": upload.newly_added_domains,
            }
        )

    return list(serialable_uploads)


def remove_last_dot(my_text):
    return my_text[0 : len(my_text) - 1] if my_text[len(my_text) - 1 : len(my_text)] == "." else my_text


@app.task(queue="storage")
def sidn_domain_upload(user, csv_data):
    """
    If the domain exists in the db, any subdomain will be added.
    As per usual, adding a subdomain will check if the domain is valid and resolvable.

    Format:
    ,2ndlevel,qname,distinct_asns
    *censored number*,arnhem.nl.,*.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,01.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfg.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,03.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,04www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfgs.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,10.255.254.35www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,12.arnhem.nl.,*censored number*
    :return:
    """

    if not csv_data:
        return

    # all mashed up in a single routine, should be separate tasks...
    upload = SIDNUpload()
    upload.at_when = datetime.now(pytz.utc)
    upload.state = "processing"
    upload.by_user = user
    upload.posted_data = csv_data
    upload.save()

    sidn_handle_domain_upload(upload.id)


@app.task(queue="storage")
def sidn_handle_domain_upload(upload_id: int):

    upload = SIDNUpload.objects.all().filter(id=upload_id).first()

    if not upload:
        return

    csv_data = upload.posted_data

    f = StringIO(csv_data)
    reader = csv.reader(f, delimiter=",")
    added = []

    for row in reader:

        if len(row) < 4:
            continue

        if row[1] == "2ndlevel":
            continue

        log.debug(f"Processing {row[2]}.")

        existing_second_level_url = (
            Url.objects.all()
            .filter(
                Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
                url=remove_last_dot(row[1]),
                is_dead=False,
            )
            .first()
        )

        if not existing_second_level_url:
            log.debug(f"Url '{remove_last_dot(row[1])}' is not in the database yet, so cannot add a subdomain.")
            continue

        if existing_second_level_url.uses_dns_wildcard:
            log.debug(f"Url '{existing_second_level_url}' uses a wildcard, so cannot verify if this is a real domain.")
            continue

        if existing_second_level_url.do_not_find_subdomains:
            log.debug(f"Url '{existing_second_level_url}' is not configures to allow new subdomains, skipping.")
            continue

        new_subdomain = remove_last_dot(row[2])

        if new_subdomain == remove_last_dot(row[1]):
            log.debug("New subdomain is the same as domain, skipping.")
            continue

        # the entire domain is included, len of new subdomain + dot (1).
        new_subdomain = new_subdomain[0 : (len(new_subdomain) - 1) - len(row[1])]

        log.debug(f"Going to try to add add {new_subdomain} as a subdomain to {row[1]}. Pending to correctness.")

        has_been_added = existing_second_level_url.add_subdomain(new_subdomain)
        if has_been_added:
            added.append(has_been_added)

    upload.state = "done"
    upload.amount_of_newly_added_domains = len(added)
    upload.newly_added_domains = [url.url for url in added]
    upload.save()


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


def update_flat_organization(flat_organization: Dict, existing_organizations=List[Organization]) -> None:
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
            else:
                url = f"{extract.domain}.{extract.suffix}"

            new_url = Url.add(url)
            new_url.organization.add(organization)
