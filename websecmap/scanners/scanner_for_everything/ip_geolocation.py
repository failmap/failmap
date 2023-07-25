import ipaddress
from typing import Any, Dict

import geoip2.webservice
from celery import group

from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.celery import app

from websecmap.scanners.models import DomainIp, GeoIp
from websecmap.scanners.time_storage import abstract_time_storage

IP_UNKNOWN = "unknown"
IP_PRIVATE = "private"
IP_GLOBAL = "global"
IP_MULTICAST = "multicast"
IP_UNSPECIFIED = "unspecified"
IP_RESERVED = "reserved"
IP_LOOPBACK = "loopback"
IP_LINK_LOCAL = "link_local"


@app.task(queue="kickoff")
def create_tasks() -> group:
    # todo: also create a task for only new ip's, as that will be cheaper and can run every day.
    # let's hope this data is accurate enough to figure out the continent.
    # add some list somewhere of what countries have what impact

    # todo: do not scan ip's of which we already know the answer, because they are in the same network.
    #  in that case use the results we already have for these networks!
    ips = (
        DomainIp.objects.all()
        .filter(is_the_latest=True)
        .exclude(ip_address__isnull=True)
        .values_list("ip_address", flat=True)
    )

    # ips can be many of the same:
    return group([scan.si(ip) | store.s() for ip in list(set(ips))])


def get_data(ip_address):
    """
    Returns:
    {
      'city': {
        'geoname_id': 5368361,
        'names': {
          'ru': 'Лос-Анджелес',
          'zh-CN': '洛杉矶',
          'de': 'Los Angeles',
          'en': 'Los Angeles',
          'es': 'Los Ángeles',
          'fr': 'Los Angeles',
          'ja': 'ロサンゼルス',
          'pt-BR': 'Los Angeles'
        }
      },
      'continent': {
        'code': 'NA',
        'geoname_id': 6255149,
        'names': {
          'en': 'North America',
          'es': 'Norteamérica',
          'fr': 'Amérique du Nord',
          'ja': '北アメリカ',
          'pt-BR': 'América do Norte',
          'ru': 'Северная Америка',
          'zh-CN': '北美洲',
          'de': 'Nordamerika'
        }
      },
      'country': {
        'iso_code': 'US',
        'geoname_id': 6252001,
        'names': {
          'es': 'Estados Unidos',
          'fr': 'États Unis',
          'ja': 'アメリカ',
          'pt-BR': 'EUA',
          'ru': 'США',
          'zh-CN': '美国',
          'de': 'Vereinigte Staaten',
          'en': 'United States'
        }
      },
      'location': {
        'accuracy_radius': 1000,
        'latitude': 34.0544,
        'longitude': -118.2441,
        'metro_code': 803,
        'time_zone': 'America/Los_Angeles'
      },
      'maxmind': {
        'queries_remaining': 83332
      },
      'postal': {
        'code': '90009'
      },
      'registered_country': {
        'iso_code': 'US',
        'geoname_id': 6252001,
        'names': {
          'de': 'Vereinigte Staaten',
          'en': 'United States',
          'es': 'Estados Unidos',
          'fr': 'États Unis',
          'ja': 'アメリカ',
          'pt-BR': 'EUA',
          'ru': 'США',
          'zh-CN': '美国'
        }
      },
      'subdivisions': [
        {
          'iso_code': 'CA',
          'geoname_id': 5332921,
          'names': {
            'zh-CN': '加州',
            'de': 'Kalifornien',
            'en': 'California',
            'es': 'California',
            'fr': 'Californie',
            'ja': 'カリフォルニア州',
            'pt-BR': 'Califórnia',
            'ru': 'Калифорния'
          }
        }
      ],
      'traits': {
        'autonomous_system_number': 15169,
        'autonomous_system_organization': 'GOOGLE',
        'isp': 'Google',
        'organization': 'Google',
        'ip_address': '8.8.8.8',
        'network': '8.8.8.8/32'
      }
    }, ['en'])`
    """

    customer_id = constance_cached_value("GEO_IP_ACCOUNT_ID")
    license_key = constance_cached_value("GEO_IP_LICENSE_KEY")

    with geoip2.webservice.Client(customer_id, license_key) as client:
        return client.city(ip_address)


@app.task(queue="internet")
def scan(ip_address: str):
    result = {"ip_address": ip_address, "designation": IP_UNKNOWN, "response_data": {}, "error": ""}

    # do not request if the IP is in a private range
    address = ipaddress.ip_address(ip_address)
    result["designation"] = ip_designation(address)

    # no use to scan, as you will not find any information
    if result["designation"] is not IP_GLOBAL:
        return result

    try:
        data = get_data(ip_address)
    except geoip2.errors.AddressNotFoundError as e:
        result["error"] = str(e)[:200]
        return result

    # use a dictionary instead of an object. It's a bit tougher with mapping but easier with storage.
    # see testcase for what fields are available in reduced data. We also don't allow serialized objects in celery
    data_dict = data.__dict__["raw"]
    log_quota_warning(data_dict)
    data_dict = reduce_maxmind_data(data_dict)

    result = map_maxmind_data_to_result(result, data_dict)
    return result


def map_maxmind_data_to_result(result, data_dict: Dict[str, Any]) -> Dict:
    result["continent_code"] = data_dict.get("continent", {}).get("code", None)
    result["continent_geoname_id"] = data_dict.get("continent", {}).get("geoname_id", None)
    result["continent_in_en"] = data_dict.get("continent", {}).get("names", {}).get("en", None)

    result["country_iso_code"] = data_dict.get("country", {}).get("iso_code", None)
    result["country_geoname_id"] = data_dict.get("country", {}).get("geoname_id", None)
    result["country_in_en"] = data_dict.get("country", {}).get("names", {}).get("en", None)

    result["city_geoname_id"] = data_dict.get("city", {}).get("geoname_id", None)
    result["city_in_en"] = data_dict.get("city", {}).get("names", {}).get("en", "")

    result["location_latitude"] = data_dict.get("location", {}).get("latitude", None)
    result["location_longitude"] = data_dict.get("location", {}).get("longitude", None)
    result["location_accuracy"] = data_dict.get("location", {}).get("accuracy_radius", None)
    result["location_metro_code"] = data_dict.get("location", {}).get("metro_code", None)

    # would this ever be not present?
    result["as_number"] = data_dict["traits"]["autonomous_system_number"]
    result["as_organization"] = data_dict["traits"]["autonomous_system_organization"]
    result["isp_name"] = data_dict["traits"]["isp"]
    result["network"] = data_dict["traits"]["network"]

    result["response_data"] = data_dict

    return result


def log_quota_warning(data_dict: Dict[str, Any]) -> None:
    # add quota warnings:
    queryies_remaining = data_dict.get("maxmind", {}).get("queries_remaining", 0)
    # don't trigger every query, but every 100.
    if queryies_remaining < 1001 and queryies_remaining % 100 == 0:
        log.error(f"Geo to IP limit reached: {queryies_remaining} queries remaining. Buy more credits.")


def reduce_maxmind_data(data_dict: Dict[str, Any]) -> Dict:
    # only English fields are guaranteed, all other are just fluctuating data
    if "city" in data_dict:
        data_dict["city"]["names"] = {"en": data_dict["city"]["names"]["en"]}

    if "continent" in data_dict:
        data_dict["continent"]["names"] = {"en": data_dict["continent"]["names"]["en"]}

    if "country" in data_dict:
        data_dict["country"]["names"] = {"en": data_dict["country"]["names"]["en"]}

    if "registered_country" in data_dict:
        data_dict["registered_country"]["names"] = {"en": data_dict["registered_country"]["names"]["en"]}

    # subdivisions are nice, but not really needed now:
    data_dict["subdivisions"] = []

    # remove the counters:
    data_dict["maxmind"] = {}

    return data_dict


def ip_designation(ip):
    # https://en.wikipedia.org/wiki/Reserved_IP_addresses
    # https://docs.python.org/3/library/ipaddress.html
    # from small to large
    if ip.is_link_local:
        return IP_LINK_LOCAL

    if ip.is_loopback:
        return IP_LOOPBACK

    if ip.is_reserved:
        return IP_RESERVED

    if ip.is_unspecified:
        return IP_UNSPECIFIED

    if ip.is_multicast:
        return IP_MULTICAST

    if ip.is_private:
        return IP_PRIVATE

    return IP_GLOBAL if ip.is_global else IP_UNKNOWN


@app.task(queue="storage")
def store(data: Dict[str, Any]):
    abstract_time_storage(
        GeoIp,
        fields_to_retrieve_latest={"ip_address": data["ip_address"]},
        fields_that_signify_change=["response_data", "designation", "error"],
        data_for_new_record=data,
    )


def update():
    # Do not update all ip's as that is costly
    # get an IP from each network, see if the network changed. If so, then get everything for that network.
    # update the whole list once a year or so
    ...
