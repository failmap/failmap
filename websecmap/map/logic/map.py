from datetime import datetime

import pytz
import simplejson as json
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.utils.text import slugify

from websecmap.map.logic.map_defaults import get_country, get_organization_type, remark
from websecmap.map.models import MapDataCache
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES


def get_reports_by_ids(ids):
    if not ids:
        return {}

    reports = {}
    cursor = connection.cursor()

    # noinspection SqlNoDataSourceInspection
    # The number of values in the IN() list is only limited by the max_allowed_packet value.
    report_sql = f"SELECT id, calculation FROM map_organizationreport WHERE id IN ({','.join(ids)})"
    cursor.execute(report_sql)
    report_rows = cursor.fetchall()
    for row in report_rows:
        reports[row[0]] = row[1]

    return reports


def get_map_data(country: str = "NL", organization_type: str = "municipality", days_back: int = 0,
                 displayed_issue: str = None):

    when = datetime.now(pytz.utc) - relativedelta(days=int(days_back))

    desired_url_scans = []
    desired_endpoint_scans = []

    if displayed_issue in URL_SCAN_TYPES:
        desired_url_scans += [displayed_issue]

    if displayed_issue in ENDPOINT_SCAN_TYPES:
        desired_endpoint_scans += [displayed_issue]

    # fallback if no data is "all", which is the default.
    if not desired_url_scans and not desired_endpoint_scans:
        desired_url_scans = URL_SCAN_TYPES
        desired_endpoint_scans = ENDPOINT_SCAN_TYPES

        # look if we have data in the cache, which will save some calculations and a slower query
        cached = MapDataCache.objects.all().filter(country=country,
                                                   organization_type=get_organization_type(organization_type),
                                                   at_when=when,
                                                   filters=['all']).first()
    else:
        # look if we have data in the cache, which will save some calculations and a slower query
        cached = MapDataCache.objects.all().filter(country=country,
                                                   organization_type=get_organization_type(organization_type),
                                                   at_when=when,
                                                   filters=desired_url_scans + desired_endpoint_scans).first()

    if cached:
        return cached.dataset

    """
    Returns a json structure containing all current map data.
    This is used by the client to render the map.

    Renditions of this dataset might be pushed to gitlab automatically.

    :return:
    """

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(pytz.utc).isoformat(),
            "data_from_time": when.isoformat(),
            "remark": remark,
            "applied filter": displayed_issue,
            "layer": organization_type,
            "country": country
        },
        "crs":
            {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features":
            [

        ]
    }

    cursor = connection.cursor()

    # Sept 2019: MySQL has an issue with mediumtext fields. When joined, and the query is not optimized, the
    # result will take 2 minutes to complete. Would you not select the mediumtext field, the query finishes in a second.
    # That is why there are two queries to retrieve map data from the database.
    sql = """
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
            coordinate_stack.stacked_coordinate_id
        FROM map_organizationreport
        INNER JOIN


          (SELECT stacked_organization.id as stacked_organization_id
          FROM organization stacked_organization
          WHERE (
            stacked_organization.created_on <= '%(when)s'
            AND stacked_organization.is_dead = 0
            AND stacked_organization.type_id=%(OrganizationTypeId)s
            AND stacked_organization.country='%(country)s'
            )
          OR (
          '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
            AND stacked_organization.is_dead = 1
            AND stacked_organization.type_id=%(OrganizationTypeId)s
            AND stacked_organization.country='%(country)s'
          )) as organization_stack
          ON organization_stack.stacked_organization_id = map_organizationreport.organization_id


        INNER JOIN
          organization on organization.id = stacked_organization_id
        INNER JOIN
          organizations_organizationtype on organizations_organizationtype.id = organization.type_id
        INNER JOIN


          (SELECT MAX(stacked_coordinate.id) as stacked_coordinate_id, area, geoJsonType, organization_id
          FROM coordinate stacked_coordinate
          INNER JOIN organization filter_organization
            ON (stacked_coordinate.organization_id = filter_organization.id)
          WHERE (
            stacked_coordinate.created_on <= '%(when)s'
            AND stacked_coordinate.is_dead = 0
            AND filter_organization.country='%(country)s'
            AND filter_organization.type_id=%(OrganizationTypeId)s
            )
          OR
            ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
            AND stacked_coordinate.is_dead = 1
            AND filter_organization.country='%(country)s'
            AND filter_organization.type_id=%(OrganizationTypeId)s
            ) GROUP BY area, organization_id
          ) as coordinate_stack
          ON coordinate_stack.organization_id = map_organizationreport.organization_id


        INNER JOIN


          (SELECT MAX(map_organizationreport.id) as stacked_organizationrating_id
          FROM map_organizationreport
          INNER JOIN organization filter_organization2
            ON (filter_organization2.id = map_organizationreport.organization_id)
          WHERE at_when <= '%(when)s'
          AND filter_organization2.country='%(country)s'
          AND filter_organization2.type_id=%(OrganizationTypeId)s
          GROUP BY organization_id
          ) as stacked_organizationrating
          ON stacked_organizationrating.stacked_organizationrating_id = map_organizationreport.id


        WHERE organization.type_id = '%(OrganizationTypeId)s' AND organization.country= '%(country)s'
        GROUP BY coordinate_stack.area, organization.name
        ORDER BY map_organizationreport.at_when ASC
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    cursor.execute(sql)
    rows = cursor.fetchall()

    needed_reports = []
    for i in rows:
        # prevent sequence item 0: expected str instance, int found
        needed_reports.append(str(i[6]))

    reports = get_reports_by_ids(needed_reports)

    # todo: http://www.gadzmo.com/python/using-pythons-dictcursor-in-mysql-to-return-a-dict-with-keys/
    # unfortunately numbered results are used. There is no decent solution for sqlite and the column to dict
    # translation is somewhat hairy. A rawquery would probably be better if possible.

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
        high, medium, low, ok = 0, 0, 0, 0

        calculation = json.loads(reports[i[6]])

        for url in calculation['organization']['urls']:
            for url_rating in url['ratings']:
                if url_rating['type'] in desired_url_scans and \
                        url_rating.get('comply_or_explain_valid_at_time_of_report', False) is False:
                    high += url_rating['high']
                    medium += url_rating['medium']
                    low += url_rating['low']
                    ok += url_rating['ok']

            # it's possible the url doesn't have ratings.
            for endpoint in url['endpoints']:
                for endpoint_rating in endpoint['ratings']:
                    if endpoint_rating['type'] in desired_endpoint_scans and \
                            endpoint_rating.get('comply_or_explain_valid_at_time_of_report', False) is False:
                        high += endpoint_rating['high']
                        medium += endpoint_rating['medium']
                        low += endpoint_rating['low']
                        ok += endpoint_rating['ok']

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
            "properties":
                {
                    "organization_id": i[5],
                    "organization_type": i[2],
                    "organization_name": i[1],
                    "organization_name_lowercase": i[1].lower(),
                    "organization_slug": slugify(i[1]),
                    "additional_keywords": extract_domains(calculation),
                    "high": high,
                    "medium": medium,
                    "low": low,
                    "data_from": when.isoformat(),
                    "severity": severity,
                    "total_urls": i[11],  # = 100%
                    "high_urls": i[12],
                    "medium_urls": i[13],
                    "low_urls": i[14],
                },
            "geometry":
                {
                    # the coordinate ID makes it easy to check if the geometry has changed shape/location.
                    "coordinate_id": i[15],

                    "type": i[4],
                    # Sometimes the data is a string, sometimes it's a list. The admin
                    # interface might influence this. The fastest would be to use a string, instead of
                    # loading some json.
                    "coordinates": proper_coordinate(i[3], i[4])
                }
        }

        # calculate some statistics, so the frontends do not have to...
        # prevent division by zero
        if i[11]:
            total_urls = int(i[11])
            high_urls = int(i[12])
            medium_urls = int(i[13])
            low_urls = int(i[14])
            dataset['properties']['percentages'] = {
                "high_urls": round(high_urls / total_urls, 2) * 100,
                "medium_urls": round(medium_urls / total_urls, 2) * 100,
                "low_urls": round(low_urls / total_urls, 2) * 100,
                "good_urls": round((total_urls - (high_urls + medium_urls + low_urls)) / total_urls, 2) * 100,
            }
        else:
            dataset['properties']['percentages'] = {
                "high_urls": 0,
                "medium_urls": 0,
                "low_urls": 0,
                "good_urls": 0,
            }

        data["features"].append(dataset)

    return data


def proper_coordinate(coordinate, geojsontype):
    # Not all data is as cleanly stored
    coordinate = json.loads(coordinate) \
        if isinstance(json.loads(coordinate), list) else json.loads(json.loads(coordinate))

    # Points in geojson are stored in lng,lat. Leaflet wants to show it the other way around.
    # https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem
    if geojsontype == "Point":
        return list(reversed(coordinate))

    return coordinate


def extract_domains(calculation):
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

    words = []

    for url in calculation['organization']['urls']:
        words += url['url'].split(".")

    # unique words only.
    words = list(set(words))

    # returned as a single string that can be searched through...
    return " ".join(words).lower()
