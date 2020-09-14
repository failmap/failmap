import logging
from math import ceil

from django.db import connection
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type, get_when, remark

log = logging.getLogger(__name__)


def get_top_win_data(country: str = "NL", organization_type="municipality", weeks_back=0):
    """
    Can't use the object.raw syntax of django. OperationalError: near "%": syntax error...
    Probably not supported, although the manual says so. Maybe because we use a multiline string?

    https://code.djangoproject.com/ticket/10070
    Dictionary params are not supported with the SQLite backend; with this backend, you must pass parameters as a list.

    When doing it right, the exception happens: format requires a mapping. Then just rely on the checks we do.
    :param country:
    :param organization_type:
    :param weeks_back:
    :return:
    """
    when = get_when(weeks_back)

    cursor = connection.cursor()
    sql = """
            SELECT
              low,
              organization.name,
              organizations_organizationtype.name,
              organization.id,
              at_when,
              organization.twitter_handle,
              high,
              medium,
              low,
              total_urls,
              total_endpoints,
              organization.is_dead
            FROM map_organizationreport
            INNER JOIN
              organization on organization.id = map_organizationreport.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
            INNER JOIN
              (
                SELECT MAX(or2.id) as id2 FROM map_organizationreport or2
                INNER JOIN organization as org2 ON org2.id = or2.organization_id
                WHERE at_when <= '%(when)s'
                  AND org2.country = '%(country)s'
                  AND org2.type_id = '%(OrganizationTypeId)s'
                GROUP BY organization_id
              ) as stacked_organization_report
            ON stacked_organization_report.id2 = map_organizationreport.id
            WHERE
              (('%(when)s' BETWEEN organization.created_on AND organization.is_dead_since
               AND organization.is_dead = 1
               ) OR (
               organization.created_on <= '%(when)s'
               AND organization.is_dead = 0
              ))
              AND organization.type_id = '%(OrganizationTypeId)s'
              AND organization.country = '%(country)s'
              AND total_urls > 0
            GROUP BY organization.name
            HAVING high = 0 AND medium = 0
            ORDER BY low ASC, total_endpoints DESC, organization.name ASC
            """ % {
        "when": when,
        "OrganizationTypeId": get_organization_type(organization_type),
        "country": get_country(country),
    }

    # log.debug(sql)
    cursor.execute(sql)
    rows = cursor.fetchall()
    return rows_to_dataset(rows, when)


def get_top_fail_data(country: str = "NL", organization_type="municipality", weeks_back=0):

    when = get_when(weeks_back)
    cursor = connection.cursor()

    sql = """
            SELECT
                low,
                organization.name,
                organizations_organizationtype.name,
                organization.id,
                at_when,
                organization.twitter_handle,
                high,
                medium,
                low,
                total_urls,
                total_endpoints
            FROM map_organizationreport
            INNER JOIN
              organization on organization.id = map_organizationreport.organization_id
            INNER JOIN
              organizations_organizationtype on organizations_organizationtype.id = organization.type_id
            INNER JOIN
              coordinate ON coordinate.organization_id = organization.id
            INNER JOIN
              (
                SELECT MAX(or2.id) as id2 FROM map_organizationreport or2
                INNER JOIN organization as org2 ON org2.id = or2.organization_id
                WHERE at_when <= '%(when)s'
                  AND org2.country = '%(country)s'
                  AND org2.type_id = '%(OrganizationTypeId)s'
                GROUP BY organization_id
              ) as stacked_organization_report
            ON stacked_organization_report.id2 = map_organizationreport.id
            WHERE
              (('%(when)s' BETWEEN organization.created_on AND organization.is_dead_since
               AND organization.is_dead = 1
               ) OR (
               organization.created_on <= '%(when)s'
               AND organization.is_dead = 0
              ))
              AND organization.type_id = '%(OrganizationTypeId)s'
              AND organization.country = '%(country)s'
              AND total_urls > 0
            GROUP BY organization.name
            HAVING high > 0 or medium > 0
            ORDER BY high DESC, medium DESC, medium DESC, organization.name ASC
            """ % {
        "when": when,
        "OrganizationTypeId": get_organization_type(organization_type),
        "country": get_country(country),
    }

    # log.debug(sql)
    cursor.execute(sql)
    rows = cursor.fetchall()
    return rows_to_dataset(rows, when)


def rows_to_dataset(rows, when):
    data = {
        "metadata": {
            "type": "toplist",
            "render_date": timezone.now(),
            "data_from_time": when,
            "remark": remark,
        },
        "ranking": [],
    }

    rank = 1
    for i in rows:
        dataset = {
            "rank": rank,
            "organization_id": i[3],
            "organization_type": i[2],
            "organization_name": i[1],
            "organization_twitter": i[5],
            "data_from": i[4],
            "high": i[6],
            "medium": i[7],
            "low": i[8],
            "total_urls": i[9],
            "total_endpoints": i[10],
            "high_div_endpoints": "%s" % ceil((int(i[6]) / int(i[10])) * 100) if i[10] else 0,
            "mid_div_endpoints": "%s" % ceil((int(i[7]) / int(i[10])) * 100) if i[10] else 0,
            "low_div_endpoints": "%s" % ceil((int(i[8]) / int(i[10])) * 100) if i[10] else 0,
            # Add all percentages, which is sort of an indication how bad / well the organization is doing overall.
            "relative": (
                ceil((int(i[6]) / int(i[10])) * 1000)
                + ceil((int(i[7]) / int(i[10])) * 100)
                + ceil((int(i[8]) / int(i[10])) * 10)
            )
            if i[10]
            else 0,
        }
        rank = rank + 1

        # je zou evt de ranking kunnen omkeren, van de totale lijst aan organisaties...
        data["ranking"].append(dataset)

    return data
