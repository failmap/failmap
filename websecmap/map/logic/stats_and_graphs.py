import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from django.db.models import Q
from django.utils import timezone

from websecmap.map.logic.map_defaults import (
    get_country,
    get_default_country,
    get_default_layer,
    get_organization_type,
    determine_when,
)
from websecmap.map.models import Configuration, HighLevelStatistic, OrganizationReport, VulnerabilityStatistic
from websecmap.organizations.models import Organization
from websecmap.reporting.models import ScanPolicy
from websecmap.reporting.severity import get_severity
from websecmap.scanners.impact import get_impact
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata

log = logging.getLogger(__package__)


def get_vulnerability_graph(country, organization_type, days_back, duration: int = 365, at_date: date = None):
    organization_type_id = get_organization_type(organization_type)
    country = get_country(country)
    when = determine_when(days_back, at_date)

    one_year_ago = when - timedelta(days=duration)

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


def get_organization_vulnerability_timeline(organization_id: int, duration: int = 365):
    one_year_ago = timezone.now() - timedelta(days=duration)

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
                "ok": rating.url_ok + rating.endpoint_ok,
            }
        )

    return stats


def get_organization_vulnerability_timeline_via_name(
    organization_name: str, organization_type: str = "", country: str = "", duration: int = 365
):
    layer = get_organization_type(organization_type) if organization_type else get_default_layer()
    country = get_country(code=country) if country else get_default_country()

    organization = (
        Organization.objects.all().filter(country=country, type=layer, name=organization_name, is_dead=False).first()
    )

    if not organization:
        return []

    return get_organization_vulnerability_timeline(organization.id, duration)


def get_stats(country, organization_type, days_back, duration: int = 365, at_date: date = None):
    """
    Stats are calculated using websecmap calculate_high_level_statistics

    :return:
    """

    when = determine_when(days_back, at_date)

    # seven queryies, but __never__ a missing result.
    stats = (
        HighLevelStatistic.objects.all()
        .filter(country=country, organization_type=get_organization_type(organization_type), at_when__lte=when)
        .order_by("-at_when")[0:duration]
    )

    reports = {"organizations": [], "urls": [], "explained": {}, "endpoints_now": 0, "endpoint": []}

    for stat in stats:
        repor = stat.report
        reports["organizations"].append(
            {"high": repor["high"], "medium": repor["medium"], "good": repor["good"], "date": stat.at_when.isoformat()}
        )
        reports["urls"].append(
            {
                "high": repor["high_urls"],
                "medium": repor["medium_urls"],
                "good": repor["good_urls"],
                "date": stat.at_when.isoformat(),
            }
        )

    first = stats.first()
    if first:
        repor = first.report
        reports["endpoint"] = repor["endpoint"]
        reports["explained"] = repor["explained"]
        reports["endpoints_now"] = repor["endpoints"]

    return reports


def what_to_improve(country: str, organization_type: str, issue_type: str):
    # todo: check if the layer is published.
    metadata = get_backend_scanmetadata()

    # Get high and medium, low stuff from policy from the scanner where where this issue_type
    conclusions_that_can_be_improved = (
        ScanPolicy.objects.all()
        .filter(scan_type=issue_type)
        .filter(Q(high__gte=1) | Q(medium__gte=1) | Q(low__gte=1))
        .values_list("conclusion", flat=True)
    )

    log.debug("Conclusions that can be improved: %s", conclusions_that_can_be_improved)

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    if issue_type in metadata["url_scan_types"]:
        return what_to_improve_ugs(country, organization_type, issue_type, conclusions_that_can_be_improved)

    return what_to_improve_epgs(country, organization_type, issue_type, conclusions_that_can_be_improved)


def what_to_improve_ugs(country: str, organization_type: str, issue_type: str, policy: List[str]):
    # todo: how to outer join on organization type and country?

    scans = UrlGenericScan.objects.all().filter(
        type=issue_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=policy,
        url__is_dead=False,
        url__not_resolvable=False,
        url__organization__country=country,
        url__organization__layers=organization_type,
    )[0:500]

    dicts = [
        {
            # "organization_id": scan.url.organization.pk,
            # "organization_name": scan.url.organization.name,
            "url_url": scan.url.url,
            "subdomain": scan.url.computed_subdomain,
            "domain": f"{scan.url.computed_domain}.{scan.url.computed_suffix}",
            "severity": get_impact(get_severity(scan)),
            "last_scan_moment": scan.last_scan_moment,
            "rating_determined_on": scan.rating_determined_on,
        }
        for scan in scans
        if get_impact(get_severity(scan)) in ["high", "medium"]
    ]

    # crude deduplication as i can't easily find out how to left outer join stuff.
    return [dict(t) for t in {tuple(d.items()) for d in dicts}]


def what_to_improve_epgs(country: str, organization_type: str, issue_type: str, policy: List[str]):
    scans = EndpointGenericScan.objects.all().filter(
        type=issue_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=policy,
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__url__organization__country=country,
        endpoint__url__organization__layers=organization_type,
    )[0:500]

    dicts = [
        {
            # "organization_id": scan.endpoint.url.organization.pk,
            # "organization_name": scan.endpoint.url.organization.name,
            "url_url": scan.endpoint.url.url,
            "subdomain": scan.endpoint.url.computed_subdomain,
            "domain": f"{scan.endpoint.url.computed_domain}.{scan.endpoint.url.computed_suffix}",
            "severity": get_impact(get_severity(scan)),
            "last_scan_moment": scan.last_scan_moment,
            "rating_determined_on": scan.rating_determined_on,
        }
        for scan in scans
        if get_impact(get_severity(scan)) in ["high", "medium"]
    ]

    # crude deduplication as i can't easily find out how to left outer join stuff.
    return [dict(t) for t in {tuple(d.items()) for d in dicts}]


def get_short_and_simple_stats(days_back: int = 0, at_date: date = None) -> Dict:
    when = determine_when(days_back, at_date)

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
