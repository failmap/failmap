import ipaddress
import re
from typing import Dict

from django.utils import timezone

from websecmap.map.logic.coordinates import attach_coordinate, switch_latlng
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url
from websecmap.scanners.models import ScanProxy


def user_is_staff_member(user):
    return user.is_active and (user.is_staff or user.is_superuser)


def operation_response(error: bool = False, success: bool = False, message: str = "", data: Dict = None):
    return {
        "error": error,
        "success": success,
        "message": message,
        "state": "error" if error else "success",
        "data": data,
        "timestamp": timezone.now(),
    }


def add_organization(data):

    if not data.get("layer", 0):
        return operation_response(error=True, message="No layer selected, cannot add organization.")

    if not data.get("country", 0):
        return operation_response(error=True, message="No country given, cannot add organization.")

    if not data.get("name", 0):
        return operation_response(error=True, message="No name given, cannot add organization.")

    if not data.get("address", 0):
        return operation_response(error=True, message="No address given, cannot add organization.")

    if not data.get("latitude", 0):
        return operation_response(error=True, message="No latitude given, cannot add organization.")

    if not data.get("longitude", 0):
        return operation_response(error=True, message="No longitude given, cannot add organization.")

    if "domains" not in data:
        return operation_response(error=True, message="Domains should be present and at least empty.")

    # prevent duplicate organizations
    if Organization.objects.all().filter(name=data["name"], country=data["country"], type__name=data["layer"]).first():
        return operation_response(
            error=True, message="Organization with this name already exists in this layer." " Preventing a duplicate."
        )

    # https://stackoverflow.com/questions/15965166/what-is-the-maximum-length-of-latitude-and-longitude
    # The valid range of latitude in degrees is -90 and +90 for the southern and northern hemisphere respectively.
    if float(data["latitude"] < -90 or float(data["latitude"]) > 90):
        return operation_response(error=True, message="Latitude is between -90 and 90.")

    # Longitude is in the range -180 and +180 specifying coordinates west and east of the Prime Meridian, respectively.
    if float(data["longitude"] < -180 or float(data["longitude"]) > 180):
        return operation_response(error=True, message="Latitude is between -180 and 180.")

    # Create the new organization
    new_organization = Organization()
    new_organization.name = data["name"]
    new_organization.address = data["address"]
    new_organization.country = data["country"]
    new_organization.type = OrganizationType.objects.all().filter(name=data["layer"]).first()
    new_organization.internal_notes = "Added via the Map admin interface."
    new_organization.created_on = timezone.now()
    new_organization.save()

    # Add a point to it:
    attach_coordinate(organization=new_organization, latitude=data["latitude"], longitude=data["longitude"])

    # The filter the added urls, and try to add them...
    if data["domains"]:
        response = add_urls(new_organization.pk, data["domains"])
        if response["error"]:
            return response

    return operation_response(
        success=True, message="Organization was added, and will be visible after creating a new" " report."
    )


def switch_lattitude_and_longitude(organization_id):
    # get the coordinate, only for point. Multipoint is not yet supported. We assume 1 alive point at a time
    # per organization.
    coord = (
        Coordinate.objects.all().filter(organization__id=organization_id, geojsontype="Point", is_dead=False).first()
    )

    if coord:
        switch_latlng(coord)
        return operation_response(
            success=True, message="Latitude and longitude are switched. Will be visible in the" " next report."
        )

    return operation_response(error=True, message="Could not find any attached coordinate that is still alive.")


def add_urls(organization_id, urls: str):
    # todo: how does it behave with urls with protocol?

    # urls is basically garbage input on multiple lines with spaces and comma's and all kinds of unicode.
    # here we try to break up this garbage into small pieces text, some are a url, some are garbage...
    urls = urls.replace(",", " ")
    urls = urls.replace("\n", " ")
    urls = urls.split(" ")
    urls = [u.strip() for u in urls]

    not_valid = []
    valid = []
    for url in urls:
        if not Url.is_valid_url(url):
            not_valid.append(url)
        else:
            valid.append(url)

    if not Organization.objects.all().filter(id=organization_id).exists():
        return operation_response(error=True, message="Organization could not be found.")

    if not valid:
        return operation_response(error=True, message="No valid url found.")

    organization = Organization.objects.all().filter(id=organization_id).first()
    for url in valid:
        organization.add_url(url)

    if not_valid:
        return operation_response(
            success=True, message=f"{len(valid)} urls have been added.", data={"invalid_domains": not_valid}
        )
    else:
        return operation_response(success=True, message=f"{len(valid)} urls have been added.")


def add_proxies(proxies: str):

    # urls is basically garbage input on multiple lines with spaces and comma's and all kinds of unicode.
    # here we try to break up this garbage into small pieces text, some are a url, some are garbage...
    proxies = proxies.replace(",", " ")
    proxies = proxies.replace("\n", " ")
    proxies = proxies.split(" ")
    proxies = [re.sub("[^0-9.:]", "", u) for u in proxies]

    not_valid = []
    valid = []
    for proxy in proxies:
        if not is_valid_ip_address_and_port(proxy):
            not_valid.append(proxy)
        else:
            valid.append(proxy)
    if not valid:
        return operation_response(error=True, message="No valid proxy found.")

    for proxy in valid:
        ScanProxy.add_address(proxy)

    if not_valid:
        return operation_response(
            success=True, message=f"{len(valid)} proxies have been added.", data={"invalid_proxies": not_valid}
        )
    else:
        return operation_response(
            success=True, message=f"{len(valid)} proxies have been added. They will be validated before use."
        )


def is_valid_ip_address_and_port(address):

    if ":" not in address:
        return False

    ip_address, port = address.split(":")

    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        return False

    try:
        port = int(port)
    except BaseException:
        # cannot cast? okbye
        return False

    if not 65535 > int(port) > 0:
        return False

    return True
