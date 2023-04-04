from datetime import date, timedelta

from constance import config

from websecmap.map.logic.map_defaults import determine_when, get_country, get_organization_type
from websecmap.map.models import OrganizationReport


def get_ticker_data(
    country: str = "NL",
    organization_type: str = "municipality",
    days_back: int = 0,
    duration: int = 10,
    at_date: date = None,
):
    # Gives ticker data of organizations, like in news scrolling:
    # On organization level, could be on URL level in the future (selecing more cool urls?)
    # Organizations are far more meaningful.
    # Amsterdam 42 +1, 32 +2, 12 -, Zutphen 12 -3, 32 -1, 3 +3, etc.

    when = determine_when(days_back, at_date)

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
            low,
            ok,
            at_when
        FROM
            map_organizationreport
        INNER JOIN
           (
                SELECT MAX(or2.id) as id2
                FROM map_organizationreport or2
                INNER JOIN organization as filter_organization
                INNER JOIN organization_layers as layers1 ON (layers1.organization_id = filter_organization.id)
                ON (filter_organization.id = or2.organization_id)
                WHERE
                    at_when <= '{when}'
                    AND filter_organization.country='{my_country}'
                    AND layers1.organizationtype_id={my_organization_type}
               GROUP BY organization_id
            ) as stacked_organizationreport
        ON stacked_organizationreport.id2 = map_organizationreport.id
        INNER JOIN organization ON map_organizationreport.organization_id = organization.id
        INNER JOIN organization_layers as layers ON (layers.organization_id = organization.id)
        WHERE
        (('{when}' BETWEEN organization.created_on AND organization.is_dead_since
           AND organization.is_dead = 1
           ) OR (
           organization.created_on <= '{when}'
           AND organization.is_dead = 0
        ))
        AND layers.organizationtype_id = '{my_organization_type}'
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
            low,
            ok,
            at_when
        FROM
               map_organizationreport
        INNER JOIN
            (
                SELECT MAX(or2.id) as id2
                FROM map_organizationreport or2
                INNER JOIN organization as filter_organization
                INNER JOIN organization_layers as layers1 ON (layers1.organization_id = filter_organization.id)
                ON (filter_organization.id = or2.organization_id)
                WHERE
                    at_when <= '{when - timedelta(days=duration)}'
                    AND filter_organization.country='{my_country}'
                    AND layers1.organizationtype_id={my_organization_type}
               GROUP BY organization_id
            ) as stacked_organizationreport
        ON stacked_organizationreport.id2 = map_organizationreport.id
        INNER JOIN organization ON map_organizationreport.organization_id = organization.id
        INNER JOIN organization_layers as layers ON (layers.organization_id = organization.id)
        WHERE
        (('{when - timedelta(days=duration)}' BETWEEN organization.created_on AND organization.is_dead_since
               AND organization.is_dead = 1
               ) OR (
               organization.created_on <= '{when - timedelta(days=duration)}'
               AND organization.is_dead = 0
        ))
        AND layers.organizationtype_id = '{my_organization_type}'
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
            "now": {
                "high": newest_urlrating.high,
                "medium": newest_urlrating.medium,
                "low": newest_urlrating.low,
                "ok": newest_urlrating.ok,
            },
        }

        try:
            matching_oldest = oldest_urlratings_dict[newest_urlrating.name]
        except KeyError:
            matching_oldest = None

        if not matching_oldest:
            score = {
                "new": True,
                "time_now": newest_urlrating.at_when,
                "time_then": None,
                "difference_in_days": None,
                "then": {"high": 0, "medium": 0, "low": 0, "ok": 0},
                "changes": {
                    "high": newest_urlrating.high,
                    "medium": newest_urlrating.medium,
                    "low": newest_urlrating.low,
                    "ok": newest_urlrating.ok,
                },
                "direction": {
                    "high": "up" if newest_urlrating.high else "steady",
                    "medium": "up" if newest_urlrating.medium else "steady",
                    "low": "up" if newest_urlrating.low else "steady",
                    "ok": "up" if newest_urlrating.ok else "steady",
                },
                "human_direction": {
                    "high": "worse" if newest_urlrating.high else "steady",
                    "medium": "worse" if newest_urlrating.medium else "steady",
                    "low": "worse" if newest_urlrating.low else "steady",
                    "ok": "better" if newest_urlrating.ok else "steady",
                },
            }

        else:
            ch_high = newest_urlrating.high - matching_oldest.high
            ch_mid = newest_urlrating.medium - matching_oldest.medium
            ch_low = newest_urlrating.low - matching_oldest.low
            ch_ok = newest_urlrating.ok - matching_oldest.ok
            score = {
                "new": False,
                "time_now": newest_urlrating.at_when,
                "time_then": matching_oldest.at_when,
                "difference_in_days": (newest_urlrating.at_when - matching_oldest.at_when).days,
                "then": {
                    "high": matching_oldest.high,
                    "medium": matching_oldest.medium,
                    "low": matching_oldest.low,
                    "ok": matching_oldest.ok,
                },
                "changes": {
                    "high": ch_high,
                    "medium": ch_mid,
                    "low": ch_low,
                    "ok": ch_ok,
                },
                "direction": {
                    "high": "up" if ch_high else "steady" if ch_high == 0 else "down",
                    "medium": "up" if ch_mid else "steady" if ch_mid == 0 else "down",
                    "low": "up" if ch_low else "steady" if ch_low == 0 else "down",
                    "ok": "up" if ch_ok else "steady" if ch_ok == 0 else "down",
                },
                "human_direction": {
                    "high": "worse" if ch_high else "steady" if ch_high == 0 else "better",
                    "medium": "worse" if ch_mid else "steady" if ch_mid == 0 else "better",
                    "low": "worse" if ch_low else "steady" if ch_low == 0 else "better",
                    "ok": "better" if ch_ok else "steady" if ch_ok == 0 else "worse",
                },
            }

        changes.append({**change, **score})

    data = {"changes": changes, "slogan": config.TICKER_SLOGAN}

    return data
