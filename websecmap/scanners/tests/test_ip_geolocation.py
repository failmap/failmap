from time import sleep

from websecmap.scanners.scanner_for_everything.ip_geolocation import (
    reduce_maxmind_data,
    log_quota_warning,
    store,
    scan,
    has_known_network,
    scan_using_known_data,
)
from websecmap.scanners.models import GeoIp, DomainIp


def test_log_quota_warning(caplog):
    log_quota_warning({"maxmind": {"queries_remaining": 999}})
    assert caplog.text == ""

    log_quota_warning({"maxmind": {"queries_remaining": 1000}})
    assert "limit reached" in caplog.text


def test_reduce_maxmind_data():
    data = {
        "city": {
            "geoname_id": 5368361,
            "names": {
                "ru": "Лос-Анджелес",
                "zh-CN": "洛杉矶",
                "de": "Los Angeles",
                "en": "Los Angeles",
                "es": "Los Ángeles",
                "fr": "Los Angeles",
                "ja": "ロサンゼルス",
                "pt-BR": "Los Angeles",
            },
        },
        "continent": {
            "code": "NA",
            "geoname_id": 6255149,
            "names": {
                "en": "North America",
                "es": "Norteamérica",
                "fr": "Amérique du Nord",
                "ja": "北アメリカ",
                "pt-BR": "América do Norte",
                "ru": "Северная Америка",
                "zh-CN": "北美洲",
                "de": "Nordamerika",
            },
        },
        "country": {
            "iso_code": "US",
            "geoname_id": 6252001,
            "names": {
                "es": "Estados Unidos",
                "fr": "États Unis",
                "ja": "アメリカ",
                "pt-BR": "EUA",
                "ru": "США",
                "zh-CN": "美国",
                "de": "Vereinigte Staaten",
                "en": "United States",
            },
        },
        "location": {
            "accuracy_radius": 1000,
            "latitude": 34.0544,
            "longitude": -118.2441,
            "metro_code": 803,
            "time_zone": "America/Los_Angeles",
        },
        "maxmind": {"queries_remaining": 83332},
        "postal": {"code": "90009"},
        "registered_country": {
            "iso_code": "US",
            "geoname_id": 6252001,
            "names": {
                "de": "Vereinigte Staaten",
                "en": "United States",
                "es": "Estados Unidos",
                "fr": "États Unis",
                "ja": "アメリカ",
                "pt-BR": "EUA",
                "ru": "США",
                "zh-CN": "美国",
            },
        },
        "subdivisions": [
            {
                "iso_code": "CA",
                "geoname_id": 5332921,
                "names": {
                    "zh-CN": "加州",
                    "de": "Kalifornien",
                    "en": "California",
                    "es": "California",
                    "fr": "Californie",
                    "ja": "カリフォルニア州",
                    "pt-BR": "Califórnia",
                    "ru": "Калифорния",
                },
            }
        ],
        "traits": {
            "autonomous_system_number": 15169,
            "autonomous_system_organization": "GOOGLE",
            "isp": "Google",
            "organization": "Google",
            "ip_address": "8.8.8.8",
            "network": "8.8.8.8/32",
        },
    }

    reduced_data = reduce_maxmind_data(data)

    assert reduced_data == {
        "city": {"geoname_id": 5368361, "names": {"en": "Los Angeles"}},
        "continent": {"code": "NA", "geoname_id": 6255149, "names": {"en": "North America"}},
        "country": {"geoname_id": 6252001, "iso_code": "US", "names": {"en": "United States"}},
        "location": {
            "accuracy_radius": 1000,
            "latitude": 34.0544,
            "longitude": -118.2441,
            "metro_code": 803,
            "time_zone": "America/Los_Angeles",
        },
        "maxmind": {},
        "postal": {"code": "90009"},
        "registered_country": {"geoname_id": 6252001, "iso_code": "US", "names": {"en": "United States"}},
        "subdivisions": [],
        "traits": {
            "autonomous_system_number": 15169,
            "autonomous_system_organization": "GOOGLE",
            "ip_address": "8.8.8.8",
            "isp": "Google",
            "network": "8.8.8.8/32",
            "organization": "Google",
        },
    }


def test_store_geo_ip(db):
    result = {"ip_address": "127.0.0.1", "designation": "loopback", "response_data": {}, "error": ""}

    # check if a scan on loopback is not started, without error as this address is to be expected
    assert scan("127.0.0.1") == result

    # first scan saves as a new scan, update and creation time are the same and is set to the latest
    store(result)
    assert GeoIp.objects.all().count() == 1
    first = GeoIp.objects.first()
    assert first.at_when == first.last_scan_moment
    assert first.is_the_latest is True

    # test if the last scan moment updates
    sleep(0.1)
    store(result)
    assert GeoIp.objects.count() == 1
    first = GeoIp.objects.first()
    assert first.at_when != first.last_scan_moment
    assert first.is_the_latest is True

    # test if the error can change, or the designation, or response data will all make different, new scans:
    # only one is the latest of the next few tests:
    store({"ip_address": "127.0.0.1", "designation": "local", "response_data": {}, "error": ""})
    assert GeoIp.objects.count() == 2
    store({"ip_address": "127.0.0.1", "designation": "local", "response_data": {"continent_code": "NL"}, "error": ""})
    assert GeoIp.objects.count() == 3
    store(
        {
            "ip_address": "127.0.0.1",
            "designation": "local",
            "response_data": {"continent_code": "NL"},
            "error": "Something went wrong",
        }
    )
    assert GeoIp.objects.count() == 4
    assert GeoIp.objects.all().filter(is_the_latest=True).count() == 1
    assert GeoIp.objects.all().filter(is_the_latest=False).count() == 3

    # you can map any data, will be no error at all if fields don't match in the 'response_data
    store(
        {
            "ip_address": "127.0.0.1",
            "designation": "local",
            "response_data": {"non-existing-field": "NL"},
            "error": "Something went wrong",
        }
    )

    # a field that does not exist is silently ignored.
    store(
        {
            "ip_address": "127.0.0.1",
            "designation": "local",
            "response_data": {"non-existing-field": "NL"},
            "error": "Something went wrong",
            "arbitrary_data": "NL",
        }
    )
    # above two things made only 1 change, as only response data changed. The arbitrary fields do not trigger
    # any changes.
    assert GeoIp.objects.count() == 5


def test_has_known_network():
    network_data = {
        "192.168.0.0/24": {"more": "data"},
        "172.20.0.0/24": {"more": "data"},
        "2001:4860::/32": {"more": "data"},
    }

    assert has_known_network("192.168.0.1", network_data) == {"more": "data"}
    assert has_known_network("192.168.2.1", network_data) is False
    assert has_known_network("2001:4860:4860::8888", network_data) == {"more": "data"}
    assert has_known_network("2000:4860:4860::8888", network_data) is False


def test_scan_using_known_data(db):
    # only the first db is known and in the db.
    # The second ip is in the same network and thus should also be geolocated
    DomainIp.objects.create(ip_address="192.168.0.1", domain="example.com", ip_version=4, is_the_latest=True)
    DomainIp.objects.create(ip_address="192.168.0.2", domain="example2.com", ip_version=4, is_the_latest=True)

    network_info = {
        "ip_address": "192.168.0.1",
        "network": "192.168.0.0/24",
        "designation": "global",
        "error": "",
        "continent_code": "NA",
        "continent_geoname_id": 6255149,
        "continent_in_en": "North America",
        "country_iso_code": "US",
        "country_geoname_id": 6252001,
        "country_in_en": "United States",
        "city_geoname_id": 4393217,
        "city_in_en": "Kansas City",
        "location_latitude": 39.1027,
        "location_longitude": -94.5778,
        "location_accuracy": 20,
        "location_metro_code": "616",
        "isp_country_code": None,
        "isp_country_geoname_id": None,
        "isp_country_in_en": None,
        "as_number": 396982,
        "as_organization": "GOOGLE-CLOUD-PLATFORM",
        "isp_name": "Google Cloud",
        "response_data": {
            "city": {"geoname_id": 4393217, "names": {"en": "Kansas City"}},
            "continent": {"code": "NA", "geoname_id": 6255149, "names": {"en": "North America"}},
            "country": {"iso_code": "US", "geoname_id": 6252001, "names": {"en": "United States"}},
            "location": {
                "accuracy_radius": 20,
                "latitude": 39.1027,
                "longitude": -94.5778,
                "metro_code": 616,
                "time_zone": "America/Chicago",
            },
            "maxmind": {},
            "postal": {"code": "64184"},
            "registered_country": {"iso_code": "US", "geoname_id": 6252001, "names": {"en": "United States"}},
            "subdivisions": [],
            "traits": {
                "autonomous_system_number": 396982,
                "autonomous_system_organization": "GOOGLE-CLOUD-PLATFORM",
                "domain": "googleusercontent.com",
                "isp": "Google Cloud",
                "organization": "Google Cloud",
                "ip_address": "34.98.91.45",
                "network": "34.98.64.0/18",
            },
        },
    }

    store(network_info)
    assert GeoIp.objects.count() == 1

    scan_using_known_data()
    assert GeoIp.objects.count() == 2
