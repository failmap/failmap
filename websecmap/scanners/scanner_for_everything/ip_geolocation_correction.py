import contextlib
import json
from datetime import timedelta
from json import JSONDecodeError
from time import sleep
from typing import List

import requests
from celery import group

from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan, GeoIpCorrection, UrlGenericScan
from websecmap.scanners.scanner_for_everything.location import (
    SCAN_TYPE_LOCATION_SERVER,
    SCAN_TYPE_LOCATION_MAIL_SERVER,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT,
    LOCATION_MEDIUM,
    LOCATION_LOW,
    LOCATION_HIGH,
)
from websecmap.scanners.time_storage import abstract_time_storage


@app.task(queue="storage", ignore_result=True)
def create_tasks():
    group([get_correction_data_for_ip_geolocation_from_ripe.si() | apply_corrections.si()]).apply_async()
    return group([])


@app.task(queue="storage", ignore_result=True)
def get_correction_data_for_ip_geolocation_from_ripe():
    """
    You can't test the whole geoip database at ripe yet, this requires permissions.
    Only get a subset of ip's that we think are wrong. This saves tons of queries.
    RIPE is the authority in the EU. The API does NOT work with IPv6.
    IPv6 corrections are now done heuristically: if the IPv4 is correct, the IPv6 is also correct.
    """
    # ripe DOES do ipv6:
    # https://apps.db.ripe.net/db-web-ui/query?searchtext=2001:67c:18a0::%2F48
    # https://apps.db.ripe.net/db-web-ui/query?searchtext=2a02:9e0::%2F32
    offending_networks_ipv4, offending_networks_ipv6 = get_offending_networks()

    # for which networks do we not have corrections yet?
    uncorrected_networks = get_uncorrected_networks(offending_networks_ipv4 + offending_networks_ipv6)

    for uncorrected_network in uncorrected_networks:
        check_ripe_for_uncorrected_network(uncorrected_network)


def check_ripe_for_uncorrected_network(uncorrected_network):
    response = call_ripe_api(uncorrected_network)
    country_code = parse_ripe_api_response(response)

    if country_code == "--":
        log.error(f"Could not get country code for network {uncorrected_network}. Ripe Response: {response}.")

    data = {"network": uncorrected_network, "country_code": country_code, "source": "ripe", "response": response}

    abstract_time_storage(
        GeoIpCorrection,
        fields_to_retrieve_latest={"network": uncorrected_network, "source": "ripe"},
        fields_that_signify_change=["country_code"],
        data_for_new_record=data,
    )


def get_relevant_scans():
    epgss = list(
        EndpointGenericScan.objects.all().filter(
            is_the_latest_scan=True,
            type__in=[SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT],
            rating__in=[LOCATION_HIGH, LOCATION_MEDIUM, LOCATION_LOW],
        )
    )

    ugss = list(
        UrlGenericScan.objects.all().filter(
            is_the_latest_scan=True,
            type__in=[SCAN_TYPE_LOCATION_SERVER, SCAN_TYPE_LOCATION_MAIL_SERVER],
            rating__in=[LOCATION_HIGH, LOCATION_MEDIUM, LOCATION_LOW],
        )
    )

    return epgss + ugss


def get_offending_networks():
    # networks that create a low, medium or high rating:
    # this list contains all networks that should be inspected. Only if they are not inspected.
    offending_networks_ipv4 = []
    offending_networks_ipv6 = []
    for epgs in get_relevant_scans():
        with contextlib.suppress(JSONDecodeError):
            evidence = json.loads(epgs.evidence)
            for record in evidence:
                network = record.get("evidence", {}).get("found_location", {}).get("network", "")
                rating = record.get("rating", "")

                if rating not in [LOCATION_HIGH, LOCATION_MEDIUM, LOCATION_LOW]:
                    continue

                if not network:
                    continue
                if ":" in network:
                    offending_networks_ipv6.append(network)
                else:
                    offending_networks_ipv4.append(network)
    return offending_networks_ipv4, offending_networks_ipv6


def get_uncorrected_networks(offending_networks: List[str], source: str = "ripe") -> List[str]:
    corrected_networks = (
        GeoIpCorrection.objects.all()
        .filter(network__in=offending_networks, is_the_latest=True, source=source)
        .values_list("network", flat=True)
    )
    return list(set(offending_networks) - set(corrected_networks))


def call_ripe_api(network: str):
    # be nice
    sleep(0.3)

    url = (
        f"https://rest.db.ripe.net/search.json?query-string={network}&type-filter=inetnum,inet6num"
        f"&flags=no-referenced&flags=no-irt&source=RIPE"
    )
    response = requests.get(url)
    return response.json()


def parse_ripe_api_response(response) -> str:
    attributes = response.get("objects", {}).get("object", [{}])[0].get("attributes", {}).get("attribute", [])

    # check if this is a non-eu / non ripe managed response. If so, the finding is probably correct.
    for attribute in attributes:
        if attribute["name"] == "descr":
            # negative results for ipv4
            if attribute["value"] == "IPv4 address block not managed by the RIPE NCC":
                return "??"

            # negative results for ipv6
            if attribute["value"] == "The whole IPv6 address space":
                return "??"

    # ripe will only give EU countries and EU country codes
    for attribute in attributes:
        if attribute["name"] == "country":
            return attribute["value"]

    # probably a rate limit or so.
    return "--"


@app.task(queue="storage", ignore_result=True)
def apply_corrections():
    apply_geoip_corrections()
    apply_ipv6_corrections()


def apply_geoip_corrections():
    # adds explanation, does not change the rating etc!
    corr = GeoIpCorrection.objects.all().filter(is_the_latest=True).exclude(country_code__in=["??", "--"]).values()
    # make it an O1 operation.
    corr_db = {corr["network"]: corr["country_code"] for corr in corr}

    for epgs in get_relevant_scans():
        with contextlib.suppress(JSONDecodeError):
            evidence = json.loads(epgs.evidence)
            for record in evidence:
                network = record.get("evidence", {}).get("found_location", {}).get("network", "")
                rating = record.get("rating", "")

                if rating not in [LOCATION_HIGH, LOCATION_MEDIUM, LOCATION_LOW]:
                    continue

                if not network:
                    continue

                # no correction available
                if network not in corr_db:
                    continue

                add_bot_explanation(epgs, "found_location_in_ip_correction_database", timedelta(days=365 * 10))


def apply_ipv6_corrections():
    # adds explanation, does not change the rating etc!
    # Not needed: if the IPv6 finding is related, it will also have an ipv4 finding which is explained.
    # and the other ipv6 networks are pretty rare and will probably be explained via mail...
    ...
