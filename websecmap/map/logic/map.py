from datetime import date, datetime, timezone
from typing import Any, Dict, List

import simplejson as json
from django.db import connection
from django.utils.text import slugify

from websecmap.app import log
from websecmap.map.logic.map_defaults import REMARK, determine_when, get_country, get_organization_type
from websecmap.map.models import MapDataCache
from websecmap.map.util import zip_to_json, transparent_json_to_zip_storage
from websecmap.organizations.models import Organization, OrganizationType
from websecmap.reporting.diskreport import retrieve_report
from websecmap.scanners.scanmetadata import get_backend_scanmetadata
import re


def get_reports_by_ids(ids: List[str]) -> Dict[str, Dict[Any, Any]]:
    reports = {}

    for report_id in ids:
        reports[report_id] = retrieve_report(report_id, "OrganizationReport")

    return reports


def get_cached_map_data(
    country: str = "NL",
    organization_type: str = "municipality",
    days_back: int = 0,
    filters: List[str] = None,
    at_date: date = None,
):
    """
    Caching is split up into two queries. This is done on purpose, as MySQL cannot deal with text fields efficiently.

    MySQL will be very slow if there are filtering conditions if there is a Textfield in the result. Even if the
    textfield is not filtered on directly.

    To given an impression: this query used to take 7 seconds with just 20.000 records in the database and 760 in
    the corresponding key. After splitting it up into two queries, the total of both would be <0.5 seconds.
    """

    # prevent mutable default
    if not filters:
        filters = ["all"]

    cached = (
        MapDataCache.objects.all()
        .filter(
            country=country,
            organization_type=get_organization_type(organization_type),
            at_when=determine_when(days_back, at_date),
            filters=filters,
        )
        .defer("dataset")
        .first()
    )

    if not cached:
        return False

    my_dataset = MapDataCache.objects.only("id", "dataset_file").get(id=cached.id)
    if not my_dataset:
        return False

    return zip_to_json(my_dataset.dataset_file)


def get_map_data(
    country: str = "NL",
    organization_type: str = "municipality",
    days_back: int = 0,
    displayed_issue: str = None,
    at_date: date = None,
):
    # A bug in the live version (possibly due to |safe) gives a Country(code='NL')} instead of
    # the country code of the country. Here this is worked around, but something is wrong and should be fixed.
    if hasattr(country, "code"):
        country = country.code

    when = determine_when(days_back, at_date)
    metadata = get_backend_scanmetadata()

    desired_url_scans = []
    desired_endpoint_scans = []

    if displayed_issue in metadata["url_scan_types"]:
        desired_url_scans += [displayed_issue]

    if displayed_issue in metadata["endpoint_scan_types"]:
        desired_endpoint_scans += [displayed_issue]

    # fallback if no data is "all", which is the default.
    if not desired_url_scans and not desired_endpoint_scans:
        desired_url_scans = metadata["url_scan_types"]
        desired_endpoint_scans = metadata["endpoint_scan_types"]

        filters = ["all"]
    else:
        filters = desired_url_scans + desired_endpoint_scans

    cached = get_cached_map_data(country, organization_type, days_back, filters, at_date)

    if cached:
        return cached

    """
    Returns a json structure containing all current map data.
    This is used by the client to render the map.

    Renditions of this dataset might be pushed to gitlab automatically.

    :return:
    """

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(timezone.utc).isoformat(),
            "data_from_time": when.isoformat(),
            "remark": REMARK,
            "applied filter": displayed_issue,
            "layer": organization_type,
            "country": country,
        },
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [],
    }

    cursor = connection.cursor()

    # Sept 2019: MySQL has an issue with mediumtext fields. When joined, and the query is not optimized, the
    # result will take 2 minutes to complete. Would you not select the mediumtext field, the query finishes in a second.
    # That is why there are two queries to retrieve map data from the database.
    my_organization_type = get_organization_type(organization_type)
    my_country = get_country(country)

    sql = f"""
        SELECT
            map_organizationreport.low,
            organization.name,
            organizations_organizationtype.name,
            coordinate_stack.area,
            coordinate_stack.geoJsonType,
            organization.id,
            map_organizationreport.id as organization_report_id,
            map_organizationreport.high,
            map_organizationreport.medium,
            map_organizationreport.low,
            map_organizationreport.total_issues,
            map_organizationreport.total_urls,
            map_organizationreport.high_urls,
            map_organizationreport.medium_urls,
            map_organizationreport.low_urls,
            coordinate_stack.stacked_coordinate_id,
            organization.city
        FROM map_organizationreport
        INNER JOIN


          (SELECT stacked_organization.id as stacked_organization_id
          FROM organization stacked_organization
          INNER JOIN organization_layers as layers4 ON (layers4.organization_id = stacked_organization.id)
          WHERE (
            stacked_organization.created_on <= '{when}'
            AND stacked_organization.is_dead = 0
            AND stacked_organization.country='{my_country}'
            AND layers4.organizationtype_id = '{my_organization_type}'
            )
          OR (
          '{when}' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
            AND stacked_organization.is_dead = 1
            AND stacked_organization.country='{my_country}'
            AND layers4.organizationtype_id = '{my_organization_type}'
          )) as organization_stack
          ON organization_stack.stacked_organization_id = map_organizationreport.organization_id


        INNER JOIN
          organization on organization.id = stacked_organization_id
      INNER JOIN
          organization_layers ON (organization_layers.organization_id = organization.id)
        INNER JOIN
          organizations_organizationtype on organizations_organizationtype.id = organization_layers.organizationtype_id
        INNER JOIN


          (SELECT MAX(stacked_coordinate.id) as stacked_coordinate_id, area, geoJsonType,
            stacked_coordinate.organization_id
          FROM coordinate stacked_coordinate
          INNER JOIN organization filter_organization
            ON (stacked_coordinate.organization_id = filter_organization.id)
          INNER JOIN organization_layers as layers3 ON (layers3.organization_id = filter_organization.id)
          WHERE (
            stacked_coordinate.created_on <= '{when}'
            AND stacked_coordinate.is_dead = 0
            AND filter_organization.country='{my_country}'
            AND layers3.organizationtype_id = '{my_organization_type}'
            )
          OR
            ('{when}' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
            AND stacked_coordinate.is_dead = 1
            AND filter_organization.country='{my_country}'
            AND layers3.organizationtype_id = '{my_organization_type}'
            ) GROUP BY area, stacked_coordinate.organization_id
          ) as coordinate_stack
          ON coordinate_stack.organization_id = map_organizationreport.organization_id


        INNER JOIN


          (SELECT MAX(map_organizationreport.id) as stacked_organizationrating_id
          FROM map_organizationreport
          INNER JOIN organization filter_organization2
            ON (filter_organization2.id = map_organizationreport.organization_id)
          INNER JOIN organization_layers as layers2 ON (layers2.organization_id = filter_organization2.id)
          WHERE at_when <= '{when}'
          AND filter_organization2.country='{my_country}'
          AND layers2.organizationtype_id = '{my_organization_type}'
          GROUP BY map_organizationreport.organization_id
          ) as stacked_organizationrating
          ON stacked_organizationrating.stacked_organizationrating_id = map_organizationreport.id

        WHERE organization_layers.organizationtype_id = '{my_organization_type}'
            AND organization.country= '{my_country}'

        GROUP BY coordinate_stack.area, organization.name
        ORDER BY map_organizationreport.at_when ASC
        """

    cursor.execute(sql)
    rows = cursor.fetchall()

    needed_reports = [str(i[6]) for i in rows]
    reports = get_reports_by_ids(needed_reports)

    # todo: http://www.gadzmo.com/python/using-pythons-dictcursor-in-mysql-to-return-a-dict-with-keys/
    # unfortunately numbered results are used. There is no decent solution for sqlite and the column to dict
    # translation is somewhat hairy. A rawquery would probably be better if possible.

    # log.error(reports)

    for i in rows:
        # Here we're going to do something stupid: to rebuild the high, medium, low classifcation based on scan_types
        # It's somewhat insane to do it like this, but it's also insane to keep adding columns for each vulnerability
        # that's added to the system. This solution will be a bit slow, but given the caching and such it wouldn't
        # hurt too much.
        # Also: we've optimized for calculation in the past, but we're not even using it until now. So that part of
        # this code is pretty optimized :)
        # This feature is created to give an instant overview of what issues are where. This will lead more clicks to
        # reports.
        # The caching of this url should be decent, as people want to click fast. Filtering on the client
        # would be possible using the calculation field. Perhaps that should be the way. Yet then we have to do
        # filtering with javascript, which is error prone (todo: this will be done in the future, as it responds faster
        # but it will also mean an enormous increase of data sent to the client.)
        # It's actually reasonably fast.
        high, medium, low, ok = 0, 0, 0, 0  # pylint: disable=invalid-name
        severity = "unknown"

        calculation = reports[str(i[6])]

        if calculation:
            for url in calculation["organization"]["urls"]:
                for url_rating in url["ratings"]:
                    if (
                        url_rating["type"] in desired_url_scans
                        and url_rating.get("comply_or_explain_valid_at_time_of_report", False) is False
                    ):
                        high += url_rating["high"]
                        medium += url_rating["medium"]
                        low += url_rating["low"]
                        ok += url_rating["ok"]  # pylint: disable=invalid-name

                # it's possible the url doesn't have ratings.
                for endpoint in url["endpoints"]:
                    for endpoint_rating in endpoint["ratings"]:
                        if (
                            endpoint_rating["type"] in desired_endpoint_scans
                            and endpoint_rating.get("comply_or_explain_valid_at_time_of_report", False) is False
                        ):
                            # what happens when the data from test_plan_outdated_scans shows up here?...
                            high += endpoint_rating["high"]
                            medium += endpoint_rating["medium"]
                            low += endpoint_rating["low"]
                            ok += endpoint_rating["ok"]  # pylint: disable=invalid-name

            # figure out if red, orange or green:
            # #162, only make things red if there is a critical issue.
            # removed json parsing of the calculation. This saves time.
            # no contents, no endpoint ever mentioned in any url (which is a standard attribute)
            if "total_urls" not in calculation["organization"] or not calculation["organization"]["total_urls"]:
                severity = "unknown"
            else:
                # things have to be OK in order to be colored. If it's all empty... then it's not OK.
                severity = "high" if high else "medium" if medium else "low" if low else "good" if ok else "unknown"

        dataset = {
            "type": "Feature",
            "properties": {
                "organization_id": i[5],
                "organization_type": i[2],
                "organization_name": i[1],
                "organization_name_lowercase": i[1].lower(),
                "organization_slug": slugify(i[1]),
                # a subquery for altnames sucks, but its less complicated than altering the query above
                # especially since group_concat works different in every database and thus will suck even harder...
                "additional_keywords": f"{extract_domains(calculation)}",
                "alternative_names": f"{get_altnames(i[5])}",
                "high": high,
                "medium": medium,
                "low": low,
                "data_from": when.isoformat(),
                "severity": severity,
                "total_urls": i[11],  # = 100%
                "high_urls": i[12],
                "medium_urls": i[13],
                "low_urls": i[14],
                "organization_city": i[16],
            },
            "geometry": {
                # the coordinate ID makes it easy to check if the geometry has changed shape/location.
                "coordinate_id": i[15],
                "type": i[4],
                # Sometimes the data is a string, sometimes it's a list. The admin
                # interface might influence this. The fastest would be to use a string, instead of
                # loading some json.
                "coordinates": proper_coordinate(i[3], i[4]),
            },
        }

        # calculate some statistics, so the frontends do not have to...
        # prevent division by zero
        if i[11]:
            total_urls = int(i[11])
            high_urls = int(i[12])
            medium_urls = int(i[13])
            low_urls = int(i[14])
            dataset["properties"]["percentages"] = {
                "high_urls": round(high_urls / total_urls, 2) * 100,
                "medium_urls": round(medium_urls / total_urls, 2) * 100,
                "low_urls": round(low_urls / total_urls, 2) * 100,
                "good_urls": round((total_urls - (high_urls + medium_urls + low_urls)) / total_urls, 2) * 100,
            }
        else:
            dataset["properties"]["percentages"] = {
                "high_urls": 0,
                "medium_urls": 0,
                "low_urls": 0,
                "good_urls": 0,
            }

        data["features"].append(dataset)

    # store the render for today
    cache_map_data_render(data, my_country, my_organization_type, filters, when.date())

    return data


def cache_map_data_render(map_data, country: str, layer_id: int, scan_type: List[str], at_when: date):
    # first calculate the new data so the time between the old record and the new one stays short
    from django.db import OperationalError

    # if the layer doesn't exist, don't magically create it.
    layer = OrganizationType.objects.all().filter(pk=layer_id).first()
    if not layer:
        return

    MapDataCache.objects.all().filter(
        at_when=at_when,
        country=country,
        organization_type=layer,
        filters=scan_type,
    ).delete()

    try:
        cached = MapDataCache()
        cached.organization_type = layer
        cached.country = country
        cached.filters = scan_type
        cached.at_when = at_when
        cached.dataset = None
        cached.dataset_file = transparent_json_to_zip_storage(map_data)
        cached.save()
    except OperationalError as my_exception:
        # The public user does not have permission to run insert statements....
        log.exception(my_exception)


def proper_coordinate(coordinate, geojsontype):
    # Not all data is as cleanly stored
    coordinate = (
        json.loads(coordinate) if isinstance(json.loads(coordinate), list) else json.loads(json.loads(coordinate))
    )

    # Points in geojson are stored in lng,lat. Leaflet wants to show it the other way around.
    # https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem
    if geojsontype == "Point":
        return list(reversed(coordinate))

    return coordinate


def get_altnames(organization_id: int) -> str:
    try:
        return " ".join(Organization.objects.get(id=organization_id).altnames)
    except Organization.DoesNotExist:
        return ""


def extract_domains(calculation) -> str:
    """
    Extracts a list of domains and subdomains from a calculation, which is then compressed to a simple version.

    For example:
    data.websecmap.example
    mysite.websecmap.example
    websecmap.example
    testsite.lan
    anothersite.testsite.lan

    will become a set of words, like this:
    data websecmap example mysite testsite lan anothersite
    """

    if not calculation:
        return ""

    words = []

    for url in calculation["organization"]["urls"]:
        words += url["url"].split(".")

    return " ".join(clean_words(words)).lower()


def clean_words(words: List[str]) -> List[str]:
    # unique words only.
    words = list(sorted(list(set(words))))

    # some words that are useless as they are available in basically all domains, which makes them not interesting
    # for search. These are the most popular subdomains ranging from 70 to several 1000+ uses.
    useless_words = [
        "www",
        "mail",
        "webmail",
        "autodiscover",
        "ftp",
        "opendata",
        "intranet",
        "feeds",
        "sip",
        "test",
        "lyncdiscover",
        "vpn",
        "mijn",
        "portal",
        "smtp",
        "remote",
        "acc",
        "adfs",
        "secure",
        "acceptatie",
        "enterpriseenrollment",
        "pop",
        "enterpriseregistration",
        "simsite",
        "digikoppeling",
        "iburgerzaken",
        "m",
        "werkplek",
        "cpanel",
        "ibzpink",
        "webdisk",
        "afspraken",
        "werkenbij",
        "login",
        "staging",
        "formulieren",
        "meet",
        "cpcalendars",
        "cpcontacts",
        "portaal",
        "hybrid",
        "loket",
        "sts",
        "preproductie",
        "edienstenburgerzaken",
        "edienstenburgerzaken-test",
        "dev",
        "api",
        "ipv6",
        "simcms",
        "dialin",
        "extranet",
        "a-www",
        "fs",
        "cms",
        "mdm",
        "mobile",
        "afspraak",
        "probeer",
        "www2",
        "oud",
        "geo",
        "mail2",
        "a-feeds",
        "a-opendata",
        "apps",
        "av",
        "support",
        "english",
        "connect",
        "msoid",
        "localhost",
        "telewerken",
        "felix",
        "beheer",
        "topdesk",
        "web",
        "owa",
        "autoconfig",
        "auth",
        "data",
        "raad",
        "ruimtelijkeplannen",
        "mobiel",
        "mx1",
        "wachtwoord",
        "magazines",
        "sftp",
        "eloket",
        "email",
        "aanmelden",
        "ipv4",
        "jaarverslag",
        "app",
        "wifi",
        "legacy",
        "feeds.english",
        "desktop",
        "old",
        "gateway",
        "beeldbank",
        "nieuwsbrief",
        "com",
        "net",
        "org",
        "nl",
    ]
    words = [word for word in words if word not in useless_words]

    # words shorter than 3 characters cannot be searched for at all
    words = [word for word in words if len(word) > 3]

    # remove ip-address related domains
    # if the word has only numbers or hyphens, it's not a domain.
    words = [word for word in words if re.match(r"^[\d\-\.]+$", word) is None]

    # if the words contain any of the followint, it's removed
    # this is for large ranges of clients in subnets
    forbidden_parts = ["kb-client"]
    words = [word for word in words if all(part not in word for part in forbidden_parts)]

    # remove system names with more than two hypens
    words = [word for word in words if word.count("-") <= 2]

    # returned as a single string that can be searched through...
    return words
