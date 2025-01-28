import json
from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import GeoIpCorrection, UrlGenericScan
from websecmap.scanners.scanner_for_everything.ip_geolocation_correction import (
    apply_geoip_corrections,
    get_correction_data_for_ip_geolocation_from_ripe,
    get_offending_networks,
    get_uncorrected_networks,
    parse_ripe_api_response,
)


def text(filepath: str):
    with open(filepath, "r") as f:
        data = f.read()
    return data


def test_get_correction_data_for_ip_geolocation_from_ripe(db, requests_mock, current_path):
    # prepare a finding:
    url = Url.objects.create(url="monitoring.basisbeveiliging.nl")

    UrlGenericScan.objects.all().create(
        url=url,
        type="location_server",
        rating="location_medium",
        explanation="location_medium",
        # adding a red hering record before and after which are OK. This insures that all records are checked
        evidence="""[
        {"rating": "location_ok", "evidence": {"found_location": {"continent_code": "AS",
        "country_iso_code": "TR", "city_in_en": "Istanbul", "as_number": 1337, "as_organization":
        "Hetzner Online GmbH", "isp_ame": "Hetzner Online", "network": "1.55.62.0/23"}, "country_rating": "unknown",
        "continent_rating": "ok"}, "domain": "monitoring.basisbeveiliging.nl"},
        {"rating": "location_medium", "evidence": {"found_location": {"continent_code": "AS",
        "country_iso_code": "TR", "city_in_en": "Istanbul", "as_number": 24940, "as_organization":
        "Hetzner Online GmbH", "isp_ame": "Hetzner Online", "network": "162.55.62.0/23"}, "country_rating": "unknown",
        "continent_rating": "medium"}, "domain": "monitoring.basisbeveiliging.nl"},
        {"rating": "location_ok", "evidence": {"found_location": {"continent_code": "AS",
        "country_iso_code": "TR", "city_in_en": "Istanbul", "as_number": 1337, "as_organization":
        "Hetzner Online GmbH", "isp_ame": "Hetzner Online", "network": "1.55.62.0/23"}, "country_rating": "unknown",
        "continent_rating": "ok"}, "domain": "monitoring.basisbeveiliging.nl"}
        ]""",
        last_scan_moment=datetime.now(timezone.utc),
        rating_determined_on=datetime.now(timezone.utc),
        is_the_latest_scan=True,
    )

    # prepare network
    content_path = f"{current_path}/websecmap/scanners/tests/ip_geolocation_correction/ripe_country_eu.json"
    requests_mock.get(
        "https://rest.db.ripe.net/search.json?query-string=162.55.62.0/23&"
        "type-filter=inetnum,inet6num&flags=no-referenced&flags=no-irt&source=RIPE",
        json=json.loads(text(content_path)),
        status_code=200,
    )

    # prechecks that happen in the correction function:
    v4, v6 = get_offending_networks()
    assert v4 == ["162.55.62.0/23"]
    assert v6 == []

    uncorrected = get_uncorrected_networks(v4)
    assert uncorrected == ["162.55.62.0/23"]

    # call the entire correction function:
    get_correction_data_for_ip_geolocation_from_ripe()
    assert GeoIpCorrection.objects.all().count() == 1

    # nothing happens when we call again:
    get_correction_data_for_ip_geolocation_from_ripe()
    assert GeoIpCorrection.objects.all().count() == 1

    first = GeoIpCorrection.objects.all().first()
    assert first.country_code == "DE"

    # network should be corrected now:
    uncorrected = get_uncorrected_networks(v4)
    assert uncorrected == []

    # apply corrections to findings
    apply_geoip_corrections()
    second = UrlGenericScan.objects.all().first()
    assert second.comply_or_explain_is_explained is True


def test_parse_ripe_api_response(current_path):
    content_path = f"{current_path}/websecmap/scanners/tests/ip_geolocation_correction/ripe_country_eu.json"
    assert parse_ripe_api_response(json.loads(text(content_path))) == "DE"

    content_path = f"{current_path}/websecmap/scanners/tests/ip_geolocation_correction/ripe_not_managed.json"
    assert parse_ripe_api_response(json.loads(text(content_path))) == "??"

    # any other error or problem causes a log message:
    assert parse_ripe_api_response({}) == "--"
