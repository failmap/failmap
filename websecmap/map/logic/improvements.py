from datetime import date, datetime, timedelta, timezone

from websecmap.map.logic.map_defaults import determine_when, get_country, get_organization_type
from websecmap.reporting.models import UrlReport


def get_improvements(country, organization_type, days_back, duration: int = 7, at_date: date = None):
    # todo: adjustable timespan
    # todo: adjustable days_back

    days_back = int(days_back)

    when = determine_when(days_back, at_date)

    # looks a lot like graphs, but then just subtract/add some values and done (?)

    # compare the first urlrating to the last urlrating
    # but do not include urls that don't exist.

    sql = f"""
        SELECT
            reporting_urlreport.id as id,
            calculation
        FROM
            reporting_urlreport
        INNER JOIN
            (
                SELECT MAX(id) as id2 FROM reporting_urlreport or2
                WHERE at_when <= '{when}' GROUP BY url_id
            ) as x
        ON x.id2 = reporting_urlreport.id
        INNER JOIN url ON reporting_urlreport.url_id = url.id
        INNER JOIN url_organization on url.id = url_organization.url_id
        INNER JOIN organization ON url_organization.organization_id = organization.id
        INNER JOIN organization_layers as layers ON (layers.organization_id = organization.id)
        WHERE layers.organizationtype_id = '{get_organization_type(organization_type)}'
        AND organization.country = '{get_country(country)}'
            """

    newest_urlratings = UrlReport.objects.raw(sql)

    # this of course doesn't work with the first day, as then we didn't measure
    # everything (and the ratings for several issues are 0...
    sql = f"""
        SELECT reporting_urlreport.id as id, calculation FROM
            reporting_urlreport
        INNER JOIN
            (
                SELECT MAX(id) as id2 FROM reporting_urlreport or2
                WHERE at_when <= '{when - timedelta(days=duration)}' GROUP BY url_id
            ) as x
        ON x.id2 = reporting_urlreport.id
        INNER JOIN url ON reporting_urlreport.url_id = url.id
        INNER JOIN url_organization on url.id = url_organization.url_id
        INNER JOIN organization ON url_organization.organization_id = organization.id
        INNER JOIN organization_layers as layers ON (layers.organization_id = organization.id)
        WHERE layers.organizationtype_id = '{get_organization_type(organization_type)}'
        AND organization.country = '{get_country(country)}'
            """

    oldest_urlratings = UrlReport.objects.raw(sql)

    old_measurement = {}
    new_measurement = {}
    scan_types = []

    # stats for the newest, should be made a function:
    for urlrating in newest_urlratings:

        # url level, why are there reports without url ratings / empty url ratings like
        if "ratings" in urlrating.calculation:
            for rating in urlrating.calculation["ratings"]:
                if rating["type"] not in new_measurement:
                    new_measurement[rating["type"]] = {"high": 0, "medium": 0, "low": 0, "ok": 0}

                if rating["type"] not in scan_types:
                    scan_types.append(rating["type"])

                new_measurement[rating["type"]]["high"] += rating["high"]
                new_measurement[rating["type"]]["medium"] += rating["medium"]
                new_measurement[rating["type"]]["low"] += rating["low"]
                new_measurement[rating["type"]]["ok"] += rating["ok"]

        if "endpoints" not in urlrating.calculation:
            continue

        for endpoint in urlrating.calculation["endpoints"]:
            for rating in endpoint["ratings"]:
                if rating["type"] not in new_measurement:
                    new_measurement[rating["type"]] = {"high": 0, "medium": 0, "low": 0, "ok": 0}

                if rating["type"] not in scan_types:
                    scan_types.append(rating["type"])

                new_measurement[rating["type"]]["high"] += rating["high"]
                new_measurement[rating["type"]]["medium"] += rating["medium"]
                new_measurement[rating["type"]]["low"] += rating["low"]
                new_measurement[rating["type"]]["ok"] += rating["ok"]

    # and the oldest stats, which should be the same function
    for urlrating in oldest_urlratings:

        if "ratings" in urlrating.calculation:
            for rating in urlrating.calculation["ratings"]:
                if rating["type"] not in old_measurement:
                    old_measurement[rating["type"]] = {"high": 0, "medium": 0, "low": 0, "ok": 0}

                if rating["type"] not in scan_types:
                    scan_types.append(rating["type"])

                old_measurement[rating["type"]]["high"] += rating["high"]
                old_measurement[rating["type"]]["medium"] += rating["medium"]
                old_measurement[rating["type"]]["low"] += rating["low"]
                old_measurement[rating["type"]]["ok"] += rating["ok"]

        if "endpoints" not in urlrating.calculation:
            continue

        for endpoint in urlrating.calculation["endpoints"]:
            for rating in endpoint["ratings"]:
                if rating["type"] not in old_measurement:
                    old_measurement[rating["type"]] = {"high": 0, "medium": 0, "low": 0, "ok": 0}

                if rating["type"] not in scan_types:
                    scan_types.append(rating["type"])

                old_measurement[rating["type"]]["high"] += rating["high"]
                old_measurement[rating["type"]]["medium"] += rating["medium"]
                old_measurement[rating["type"]]["low"] += rating["low"]
                old_measurement[rating["type"]]["ok"] += rating["ok"]

    # and now do some magic to see the changes in this timespan:
    changes = {}
    for scan_type in scan_types:
        if scan_type not in changes:
            changes[scan_type] = {}

        if scan_type not in old_measurement:
            old_measurement[scan_type] = {}

        if scan_type not in new_measurement:
            new_measurement[scan_type] = {}

        changes[scan_type] = {
            "old": {
                "date": datetime.now(timezone.utc) - timedelta(days=duration),
                "high": old_measurement[scan_type].get("high", 0),
                "medium": old_measurement[scan_type].get("medium", 0),
                "low": old_measurement[scan_type].get("low", 0),
                "ok": old_measurement[scan_type].get("ok", 0),
            },
            "new": {
                "date": when,
                "high": new_measurement[scan_type].get("high", 0),
                "medium": new_measurement[scan_type].get("medium", 0),
                "low": new_measurement[scan_type].get("low", 0),
                "ok": new_measurement[scan_type].get("ok", 0),
            },
            "improvements": {
                "high": old_measurement[scan_type].get("high", 0) - new_measurement[scan_type].get("high", 0),
                "medium": old_measurement[scan_type].get("medium", 0) - new_measurement[scan_type].get("medium", 0),
                "low": old_measurement[scan_type].get("low", 0) - new_measurement[scan_type].get("low", 0),
                "ok": old_measurement[scan_type].get("ok", 0) - new_measurement[scan_type].get("ok", 0),
            },
        }

    # and now for overall changes, what everyone is coming for...
    for scan_type in scan_types:
        changes["overall"] = {
            "old": {
                "high": changes.get("overall", {}).get("old", {}).get("high", 0) + changes[scan_type]["old"]["high"],
                "medium": changes.get("overall", {}).get("old", {}).get("medium", 0)
                + changes[scan_type]["old"]["medium"],
                "low": changes.get("overall", {}).get("old", {}).get("low", 0) + changes[scan_type]["old"]["low"],
                "ok": changes.get("overall", {}).get("old", {}).get("ok", 0) + changes[scan_type]["old"]["ok"],
            },
            "new": {
                "high": changes.get("overall", {}).get("new", {}).get("high", 0) + changes[scan_type]["new"]["high"],
                "medium": changes.get("overall", {}).get("new", {}).get("medium", 0)
                + changes[scan_type]["new"]["medium"],
                "low": changes.get("overall", {}).get("new", {}).get("low", 0) + changes[scan_type]["new"]["low"],
                "ok": changes.get("overall", {}).get("new", {}).get("ok", 0) + changes[scan_type]["new"]["ok"],
            },
            "improvements": {
                "high": changes.get("overall", {}).get("improvements", {}).get("high", 0)
                + changes[scan_type]["improvements"]["high"],
                "medium": changes.get("overall", {}).get("improvements", {}).get("medium", 0)
                + changes[scan_type]["improvements"]["medium"],
                "low": changes.get("overall", {}).get("improvements", {}).get("low", 0)
                + changes[scan_type]["improvements"]["low"],
                "ok": changes.get("overall", {}).get("improvements", {}).get("ok", 0)
                + changes[scan_type]["improvements"]["ok"],
            },
        }

    return changes
