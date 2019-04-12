from datetime import datetime

import pytz
import simplejson as json
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.utils.text import slugify

from websecmap.map.logic.map_defaults import get_country, get_organization_type, remark
from websecmap.map.models import MapDataCache
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES


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
            "render_date": datetime.now(pytz.utc),
            "data_from_time": when,
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

    # instant answer, 0.16 sec answer (mainly because of the WHEN <= date subquery.
    # This could be added to a standerd django query manager, with an extra join. It's fast.
    # sometimes 0.01 second :) And also works in sqlite. Hooray.

    # ID Order should not matter, esp in async rebuild situations. It does now.

    # The calculation is being grabbed in a separate join to speed up MySQL: the calculation field is a longtext
    # that forces mysql to use disk cache as the result set is matched on to temporary tables etc.
    # So, therefore we're joining in the calculation on the last moment. Then the query just takes two seconds (still
    # slower than sqlite), but by far more acceptable than 68 seconds. This is about or3. This approach makes sqllite
    # a bit slower it seems, but still well within acceptable levels.
    sql = """
        SELECT
            map_organizationreport.low,
            organization.name,
            organizations_organizationtype.name,
            coordinate_stack.area,
            coordinate_stack.geoJsonType,
            organization.id,
            or3.calculation,
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
          (SELECT id as stacked_organization_id
          FROM organization stacked_organization
          WHERE (stacked_organization.created_on <= '%(when)s' AND stacked_organization.is_dead = 0)
          OR (
          '%(when)s' BETWEEN stacked_organization.created_on AND stacked_organization.is_dead_since
          AND stacked_organization.is_dead = 1)) as organization_stack
          ON organization_stack.stacked_organization_id = map_organizationreport.organization_id
        INNER JOIN
          organization on organization.id = stacked_organization_id
        INNER JOIN
          organizations_organizationtype on organizations_organizationtype.id = organization.type_id
        INNER JOIN
          (SELECT MAX(id) as stacked_coordinate_id, area, geoJsonType, organization_id
          FROM coordinate stacked_coordinate
          WHERE (stacked_coordinate.created_on <= '%(when)s' AND stacked_coordinate.is_dead = 0)
          OR
          ('%(when)s' BETWEEN stacked_coordinate.created_on AND stacked_coordinate.is_dead_since
          AND stacked_coordinate.is_dead = 1) GROUP BY organization_id) as coordinate_stack
          ON coordinate_stack.organization_id = map_organizationreport.organization_id
        INNER JOIN
          (SELECT MAX(id) as stacked_organizationrating_id FROM map_organizationreport
          WHERE at_when <= '%(when)s' GROUP BY organization_id) as stacked_organizationrating
          ON stacked_organizationrating.stacked_organizationrating_id = map_organizationreport.id
        INNER JOIN map_organizationreport as or3 ON or3.id = map_organizationreport.id
        WHERE organization.type_id = '%(OrganizationTypeId)s' AND organization.country= '%(country)s'
        GROUP BY coordinate_stack.area, organization.name
        ORDER BY map_organizationreport.at_when ASC
        """ % {"when": when, "OrganizationTypeId": get_organization_type(organization_type),
               "country": get_country(country)}

    # coordinate_stack was also grouped by area, which doesn't help if there are updates: if the type of shape changes
    # then the area is selected for each type of shape (since the filter is both true for now and the past). Thus
    # removing area grouping will make sure that the share type can change without delivering double results.
    # You can test this with dutch provinces, who where imported as a different type suddenly. When loading the data
    # the map showed old and new coordinates on and off, meaning the result was semi-random somewhere. This was due to
    # area being in the stack. See change on issue #130. All maps seemed to be correct over time after this change still

    # print(sql)

    # with the new solution, you only get just ONE area result per organization... -> nope, group by area :)
    cursor.execute(sql)

    rows = cursor.fetchall()

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

        calculation = json.loads(i[6])

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
                    "organization_slug": slugify(i[1]),
                    "high": high,
                    "medium": medium,
                    "low": low,
                    "data_from": when,
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
                    # interface might influence this.
                    "coordinates":
                        json.loads(i[3]) if isinstance(json.loads(i[3]), list)
                        else json.loads(json.loads(i[3]))  # hack :)
                }
        }

        data["features"].append(dataset)

    return data
