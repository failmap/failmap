from datetime import timedelta

from constance import config

from websecmap.map.logic.map_defaults import get_country, get_organization_type, get_when
from websecmap.map.models import OrganizationReport


def get_ticker_data(
    country: str = "NL", organization_type: str = "municipality", weeks_back: int = 0, weeks_duration: int = 0
):

    weeks_back = int(weeks_back)
    weeks_duration = int(weeks_duration)

    # Gives ticker data of organizations, like in news scrolling:
    # On organization level, could be on URL level in the future (selecing more cool urls?)
    # Organizations are far more meaningful.
    # Amsterdam 42 +1, 32 +2, 12 -, Zutphen 12 -3, 32 -1, 3 +3, etc.

    if not weeks_duration:
        weeks_duration = 10

    when = get_when(weeks_back)

    # looks a lot like graphs, but then just subtract/add some values and done (?)

    # compare the first urlrating to the last urlrating
    # but do not include urls that don't exist.

    my_organization_type = get_organization_type(organization_type)
    my_country = get_country(country)
    sql = f"""
        SELECT
            map_organizationreport.id as id,
            name,
            high,
            medium,
            low
        FROM
            map_organizationreport
        INNER JOIN
           (
                SELECT MAX(or2.id) as id2
                FROM map_organizationreport or2
                INNER JOIN organization as filter_organization
                ON (filter_organization.id = or2.organization_id)
                WHERE
                    at_when <= '{when}'
                    AND filter_organization.country='{my_country}'
                    AND filter_organization.type_id={my_organization_type}
               GROUP BY organization_id
            ) as stacked_organizationreport
        ON stacked_organizationreport.id2 = map_organizationreport.id
        INNER JOIN organization ON map_organizationreport.organization_id = organization.id
        WHERE
        (('{when}' BETWEEN organization.created_on AND organization.is_dead_since
           AND organization.is_dead = 1
           ) OR (
           organization.created_on <= '{when}'
           AND organization.is_dead = 0
        ))
        AND organization.type_id = '{my_organization_type}'
        AND organization.country = '{my_country}'
        AND total_urls > 0
        """

    newest_urlratings = list(OrganizationReport.objects.raw(sql))

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    my_organization_type = get_organization_type(organization_type)
    my_country = get_country(country)
    sql = f"""
        SELECT
            map_organizationreport.id as id,
            name,
            high,
            medium,
            low
        FROM
               map_organizationreport
        INNER JOIN
            (
                SELECT MAX(or2.id) as id2
                FROM map_organizationreport or2
                INNER JOIN organization as filter_organization
                ON (filter_organization.id = or2.organization_id)
                WHERE
                    at_when <= '{when - timedelta(days=(weeks_duration * 7))}'
                    AND filter_organization.country='{my_country}'
                    AND filter_organization.type_id={my_organization_type}
               GROUP BY organization_id
            ) as stacked_organizationreport
        ON stacked_organizationreport.id2 = map_organizationreport.id
        INNER JOIN organization ON map_organizationreport.organization_id = organization.id
        WHERE
        (('{when - timedelta(days=(weeks_duration * 7))}' BETWEEN organization.created_on AND organization.is_dead_since
               AND organization.is_dead = 1
               ) OR (
               organization.created_on <= '{when - timedelta(days=(weeks_duration * 7))}'
               AND organization.is_dead = 0
        ))
        AND organization.type_id = '{my_organization_type}'
        AND organization.country = '{my_country}'
        AND total_urls > 0
        """

    oldest_urlratings = list(OrganizationReport.objects.raw(sql))

    # create a dict, where the keys are pointing to the ratings. This makes it easy to match the
    # correct ones. And handle missing oldest ratings for example.
    oldest_urlratings_dict = {}
    for oldest_urlrating in oldest_urlratings:
        oldest_urlratings_dict[oldest_urlrating.name] = oldest_urlrating

    # Unsuccessful rebuild? Or not enough organizations?
    if not newest_urlratings:
        return {"changes": {}, "slogan": config.TICKER_SLOGAN}

    changes = []
    for newest_urlrating in newest_urlratings:

        change = {
            "organization": newest_urlrating.name,
            "high_now": newest_urlrating.high,
            "medium_now": newest_urlrating.medium,
            "low_now": newest_urlrating.low,
        }

        try:
            matching_oldest = oldest_urlratings_dict[newest_urlrating.name]
        except KeyError:
            matching_oldest = None

        if not matching_oldest:
            change["high_then"] = "-"
            change["medium_then"] = "-"
            change["low_then"] = "-"
            change["high_changes"] = newest_urlrating.high
            change["medium_changes"] = newest_urlrating.medium
            change["low_changes"] = newest_urlrating.low

        else:
            change["high_then"] = matching_oldest.high
            change["medium_then"] = matching_oldest.medium
            change["low_then"] = matching_oldest.low
            change["high_changes"] = newest_urlrating.high - matching_oldest.high
            change["medium_changes"] = newest_urlrating.medium - matching_oldest.medium
            change["low_changes"] = newest_urlrating.low - matching_oldest.low

        changes.append(change)

    data = {"changes": changes, "slogan": config.TICKER_SLOGAN}

    return data
