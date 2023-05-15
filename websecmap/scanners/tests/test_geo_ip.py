from time import sleep


from websecmap.scanners.geo_ip import reduce_maxmind_data, log_quota_warning, store, scan
from websecmap.scanners.models import GeoIp


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
