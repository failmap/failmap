from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

import pytz
from dateutil.relativedelta import relativedelta
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_default_country, get_default_layer, get_organization_type
from websecmap.map.models import Configuration, HighLevelStatistic, OrganizationReport, VulnerabilityStatistic
from websecmap.organizations.models import Organization
from websecmap.reporting.severity import get_severity
from websecmap.scanners import POLICY, URL_SCAN_TYPES
from websecmap.scanners.impact import get_impact
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
import logging

log = logging.getLogger(__package__)


def get_vulnerability_graph(country, organization_type, weeks_back):

    organization_type_id = get_organization_type(organization_type)
    country = get_country(country)
    when = timezone.now() - relativedelta(weeks=int(weeks_back))

    one_year_ago = when - timedelta(days=365)

    data = (
        VulnerabilityStatistic.objects.all()
        .filter(organization_type=organization_type_id, country=country, at_when__lte=when, at_when__gte=one_year_ago)
        .order_by("scan_type", "at_when")
    )

    """
    Desired output:
      "security_headers_x_frame_options": [
        {
          "date": "2018-07-17",
          "high": 0,
          "medium": 3950,
          "low": 0
        },
        {
          "date": "2018-07-24",
          "high": 0,
          "medium": 2940,
          "low": 0
        },
    """
    stats = {}

    for statistic in data:
        if statistic.scan_type not in stats:
            stats[statistic.scan_type] = []

        stats[statistic.scan_type].append(
            {
                "high": statistic.high,
                "medium": statistic.medium,
                "low": statistic.low,
                "date": statistic.at_when.isoformat(),
                "urls": statistic.urls,
                "ok_urls": statistic.ok_urls,
                "endpoints": statistic.endpoints,
                "ok_endpoints": statistic.ok_endpoints,
                "ok": statistic.ok,
            }
        )

    return stats


def get_organization_vulnerability_timeline(organization_id: int):
    one_year_ago = timezone.now() - timedelta(days=365)

    ratings = (
        OrganizationReport.objects.all()
        .filter(organization=organization_id, at_when__gte=one_year_ago)
        .order_by("at_when")
    )

    stats = []

    for rating in ratings:
        stats.append(
            {
                "date": rating.at_when.date().isoformat(),
                "endpoints": rating.total_endpoints,
                "urls": rating.total_urls,
                "high": rating.url_issues_high + rating.endpoint_issues_high,
                "medium": rating.url_issues_medium + rating.endpoint_issues_medium,
                "low": rating.url_issues_low + rating.endpoint_issues_low,
            }
        )

    return stats


def get_organization_vulnerability_timeline_via_name(
    organization_name: str, organization_type: str = "", country: str = ""
):

    layer = get_organization_type(organization_type) if organization_type else get_default_layer()
    country = get_country(code=country) if country else get_default_country()

    organization = (
        Organization.objects.all().filter(country=country, type=layer, name=organization_name, is_dead=False).first()
    )

    if not organization:
        return {}

    return get_organization_vulnerability_timeline(organization.id)


def stats_determine_when(stat, weeks_back=0):
    if stat == "now" or stat == "earliest":
        when = datetime.now(pytz.utc)
    else:
        value, unit, _ = stat.split()
        when = datetime.now(pytz.utc) - relativedelta(**{unit: int(value)})

    # take into account the starting point
    # eg: now = 1 march, starting point: 1 january. Difference is N days. Subtract N from when.
    if weeks_back:
        when = when - relativedelta(weeks=int(weeks_back))

    # optimize: always give back the time 00:00:00, so the query result can be cached as the same query is
    # performed every time.
    dt = datetime(year=when.year, month=when.month, day=when.day, hour=0, minute=0, second=0, tzinfo=pytz.utc)
    # log.debug("%s: %s (%s weeks back)" % (stat, dt, weeks_back))
    return dt


def get_stats_outdated(country, organization_type, weeks_back):
    """
    Stats are calculated using websecmap calculate_high_level_statistics

    :param country:
    :param organization_type:
    :param weeks_back:
    :return:
    """

    timeframes = {
        "now": 0,
        "7 days ago": 0,
        "2 weeks ago": 0,
        "3 weeks ago": 0,
        "1 months ago": 0,
        "2 months ago": 0,
        "3 months ago": 0,
    }

    reports = {}
    for stat in timeframes:
        when = stats_determine_when(stat, weeks_back).date()

        # seven queryies, but __never__ a missing result.
        stats = (
            HighLevelStatistic.objects.all()
            .filter(country=country, organization_type=get_organization_type(organization_type), at_when__lte=when)
            .order_by("-at_when")
            .first()
        )

        # no stats before a certain date, or database empty.
        if stats:
            reports[stat] = stats.report

    return reports


def get_stats(country, organization_type, weeks_back):
    """
    Stats are calculated using websecmap calculate_high_level_statistics

    :param country:
    :param organization_type:
    :param weeks_back:
    :return:
    """

    when = datetime.now(pytz.utc) - relativedelta(days=int(weeks_back * 7))

    # seven queryies, but __never__ a missing result.
    stats = (
        HighLevelStatistic.objects.all()
        .filter(country=country, organization_type=get_organization_type(organization_type), at_when__lte=when)
        .order_by("-at_when")[0:366]
    )

    reports = {"organizations": [], "urls": [], "explained": {}, "endpoints_now": 0, "endpoint": []}

    for stat in stats:
        r = stat.report
        reports["organizations"].append(
            {"high": r["high"], "medium": r["medium"], "good": r["good"], "date": stat.at_when.isoformat()}
        )
        reports["urls"].append(
            {
                "high": r["high_urls"],
                "medium": r["medium_urls"],
                "good": r["good_urls"],
                "date": stat.at_when.isoformat(),
            }
        )

    first = stats.first()
    if first:
        r = first.report
        reports["endpoint"] = r["endpoint"]
        reports["explained"] = r["explained"]
        reports["endpoints_now"] = r["endpoints"]

    return reports


def what_to_improve(country: str, organization_type: str, issue_type: str):
    # todo: check if the layer is published.

    policy = POLICY.get(issue_type, None)
    if not policy:
        log.debug(f"No policy found for {issue_type}")
        return []

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    if issue_type in URL_SCAN_TYPES:
        return what_to_improve_ugs(country, organization_type, issue_type, policy)
    else:
        return what_to_improve_epgs(country, organization_type, issue_type, policy)


def what_to_improve_ugs(country: str, organization_type: str, issue_type: str, policy):
    scans = UrlGenericScan.objects.all().filter(
        type=issue_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=policy["high"] + policy["medium"],
        url__is_dead=False,
        url__not_resolvable=False,
        url__organization__country=country,
        url__organization__type=organization_type,
    )[0:1000]

    return [
        {
            # "organization_id": scan.url.organization.pk,
            # "organization_name": scan.url.organization.name,
            "url_url": scan.url.url,
            "severity": get_impact(get_severity(scan)),
            "last_scan_moment": scan.last_scan_moment,
            "rating_determined_on": scan.rating_determined_on,
        }
        for scan in scans
        if get_impact(get_severity(scan)) in ["high", "medium"]
    ]


def what_to_improve_epgs(country: str, organization_type: str, issue_type: str, policy):
    scans = EndpointGenericScan.objects.all().filter(
        type=issue_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=policy["high"] + policy["medium"],
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__url__organization__country=country,
        endpoint__url__organization__type=organization_type,
    )[0:500]

    return [
        {
            # "organization_id": scan.endpoint.url.organization.pk,
            # "organization_name": scan.endpoint.url.organization.name,
            "url_url": scan.endpoint.url.url,
            "severity": get_impact(get_severity(scan)),
            "last_scan_moment": scan.last_scan_moment,
            "rating_determined_on": scan.rating_determined_on,
        }
        for scan in scans
        if get_impact(get_severity(scan)) in ["high", "medium"]
    ]


def get_short_and_simple_stats(weeks_back: int = 0) -> Dict:
    when = datetime.now(pytz.utc) - relativedelta(days=int(weeks_back * 7))

    configurations = Configuration.objects.all().filter(is_displayed=True).order_by("display_order")

    simplestat = defaultdict(dict)

    for configuration in configurations:

        stats = (
            HighLevelStatistic.objects.all()
            .filter(country=configuration.country, organization_type=configuration.organization_type, at_when__lte=when)
            .order_by("-at_when")
            .first()
        )

        if stats:
            simplestat[configuration.country.code][configuration.organization_type.name] = {
                "country_code": configuration.country.code,
                "country_name": configuration.country.name,
                "country_flag": configuration.country.flag,
                "layer": configuration.organization_type.name,
                "organizations": stats.report["total_organizations"],
                "urls": stats.report["total_urls"],
                "services": stats.report["endpoints"],
                "high percentage": stats.report["high percentage"],
                "medium percentage": stats.report["medium percentage"],
                "good percentage": stats.report["good percentage"],
                "high url percentage": stats.report["high url percentage"],
                "medium url percentage": stats.report["medium url percentage"],
                "good url percentage": stats.report["good url percentage"],
            }

    return simplestat
