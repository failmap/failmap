from datetime import datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta
from django.utils import timezone

from websecmap.map.logic.map_defaults import (get_country, get_default_country, get_default_layer,
                                              get_organization_type)
from websecmap.map.models import HighLevelStatistic, OrganizationReport, VulnerabilityStatistic
from websecmap.organizations.models import Organization


def get_vulnerability_graph(country, organization_type, weeks_back):

    organization_type_id = get_organization_type(organization_type)
    country = get_country(country)
    when = timezone.now() - relativedelta(weeks=int(weeks_back))

    one_year_ago = when - timedelta(days=365)

    data = VulnerabilityStatistic.objects.all().filter(
        organization_type=organization_type_id, country=country, at_when__lte=when, at_when__gte=one_year_ago
    ).order_by('scan_type', 'at_when')

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
            {'high': statistic.high,
             'medium': statistic.medium,
             'low': statistic.low,
             'date': statistic.at_when.isoformat(),
             'urls': statistic.urls,
             'ok_urls': statistic.ok_urls,
             'endpoints': statistic.endpoints,
             'ok_endpoints': statistic.ok_endpoints,
             'ok': statistic.ok
             })

    return stats


def get_organization_vulnerability_timeline(organization_id: int):
    one_year_ago = timezone.now() - timedelta(days=365)

    ratings = OrganizationReport.objects.all().filter(organization=organization_id,
                                                      at_when__gte=one_year_ago).order_by('at_when')

    stats = []

    for rating in ratings:
        stats.append({'date': rating.at_when.date().isoformat(),
                      'endpoints': rating.total_endpoints,
                      'urls': rating.total_urls,
                      'high': rating.url_issues_high + rating.endpoint_issues_high,
                      'medium': rating.url_issues_medium + rating.endpoint_issues_medium,
                      'low': rating.url_issues_low + rating.endpoint_issues_low})

    return stats


def get_organization_vulnerability_timeline_via_name(
        organization_name: str, organization_type: str = "", country: str = ""):

    layer = get_organization_type(organization_type) if organization_type else get_default_layer()
    country = get_country(code=country) if country else get_default_country()

    organization = Organization.objects.all().filter(
        country=country,
        type=layer,
        name=organization_name,
        is_dead=False
    ).first()

    if not organization:
        return {}

    return get_organization_vulnerability_timeline(organization.id)


def stats_determine_when(stat, weeks_back=0):
    if stat == 'now' or stat == 'earliest':
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

    timeframes = {'now': 0, '7 days ago': 0, '2 weeks ago': 0, '3 weeks ago': 0,
                  '1 months ago': 0, '2 months ago': 0, '3 months ago': 0}

    reports = {}
    for stat in timeframes:
        when = stats_determine_when(stat, weeks_back).date()

        # seven queryies, but __never__ a missing result.
        stats = HighLevelStatistic.objects.all().filter(
            country=country,
            organization_type=get_organization_type(organization_type),
            at_when__lte=when
        ).order_by('-at_when').first()

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

    when = datetime.now(pytz.utc) - relativedelta(days=int(weeks_back*7))

    # seven queryies, but __never__ a missing result.
    stats = HighLevelStatistic.objects.all().filter(
        country=country,
        organization_type=get_organization_type(organization_type),
        at_when__lte=when
    ).order_by('-at_when')[0:366]

    reports = {'organizations': [], 'urls': [], 'explained': {}, 'endpoints_now': 0, 'endpoint': []}

    for stat in stats:
        r = stat.report
        reports['organizations'].append({'high': r['high'], 'medium': r['medium'], 'good': r['good'],
                                         'date': stat.at_when.isoformat()})
        reports['urls'].append({'high': r['high_urls'], 'medium': r['medium_urls'], 'good': r['good_urls'],
                                'date': stat.at_when.isoformat()})

    first = stats.first()
    if first:
        r = first.report
        reports['endpoint'] = r['endpoint']
        reports['explained'] = r['explained']
        reports['endpoints_now'] = r['endpoints']

    return reports
