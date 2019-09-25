
import ipaddress
import re
from typing import Dict

from django.utils import timezone

from websecmap.map.logic.coordinates import switch_latlng
from websecmap.organizations.models import Coordinate, Organization, Url
from websecmap.scanners.models import ScanProxy


def user_is_staff_member(user):
    return user.is_active and (user.is_staff or user.is_superuser)


def operation_response(error: bool = False, success: bool = False, message: str = "", data: Dict = None):
    return {'error': error,
            'success': success,
            'message': message,
            'state': "error" if error else "success",
            'data': data,
            'timestamp': timezone.now()
            }


def switch_lattitude_and_longitude(organization_id):
    # get the coordinate, only for point. Multipoint is not yet supported. We assume 1 alive point at a time
    # per organization.
    coord = Coordinate.objects.all().filter(
        organization__id=organization_id, geojsontype="Point", is_dead=False).first()

    if coord:
        switch_latlng(coord)
        return operation_response(success=True, message='Latitude and longitude are switched. Will be visible in the'
                                                        ' next report.')

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
        return operation_response(error=True, message='Organization could not be found.')

    if not valid:
        return operation_response(error=True, message='No valid url found.')

    organization = Organization.objects.all().filter(id=organization_id).first()
    for url in valid:
        organization.add_url(url)

    if not_valid:
        return operation_response(
            success=True,
            message=f'{len(valid)} urls have been added.',
            data={'invalid_domains': not_valid}
        )
    else:
        return operation_response(success=True, message=f'{len(valid)} urls have been added.')


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
        return operation_response(error=True, message='No valid proxy found.')

    for proxy in valid:
        ScanProxy.add_address(proxy)

    if not_valid:
        return operation_response(
            success=True,
            message=f'{len(valid)} proxies have been added.',
            data={'invalid_proxies': not_valid}
        )
    else:
        return operation_response(
            success=True,
            message=f'{len(valid)} proxies have been added. They will be validated before use.')


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
