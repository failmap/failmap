import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import dateutil.parser
import pytz

from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.map_configs import filter_map_configs, retrieve
from websecmap.map.models import Configuration, MapHealthReport, OrganizationReport
from websecmap.organizations.models import Organization

OUTDATED_HOURS = 24 * 7

log = logging.getLogger(__name__)


"""
Retrieves all reports of a map, and will determine the health of those reports to a single percentage.

Everything before OUTDATED_HOURS is wrong. So with 200 OUTDATED_HOURS of 400 total, the grade is 50%.
If there are no reports, the grade is 0%.

This grade gets stored inside a model related to a certain map, so the metric can be retrieved over time.
"""


@app.task(queue="reporting")
def update_map_health_reports(published_scan_types,
                              days: int = 366, countries: List = None, organization_types: List = None):

    map_configurations = filter_map_configs(countries=countries, organization_types=organization_types)
    for map_configuration in map_configurations:
        organization_type_id = map_configuration['organization_type']
        country = map_configuration['country']

        organizations_on_map = Organization.objects.all().filter(
            country=country, type=organization_type_id)

        for days_back in list(reversed(range(0, days))):
            total_outdated = []
            total_good = []
            old_date = datetime.now(pytz.utc) - timedelta(days=days_back)

            log.debug(f"Creating health report of {days_back} days back.")
            for organization in organizations_on_map:
                # log.debug(f"Creating health report of {organization} at {old_date}.")
                latest_report = get_latest_report_of_organization(organization, old_date)
                if not latest_report:
                    continue

                # log.debug(f"The latest report of {organization} at {old_date} is from {latest_report.at_when}.")

                ratings_outdated, ratings_good = split_ratings_between_good_and_bad(latest_report, OUTDATED_HOURS)
                total_outdated += ratings_outdated
                total_good += ratings_good

            report = \
                create_health_report(total_outdated, total_good, published_scan_types)
            # Update reports of a certain day. For example when the report for a single day is re-generated.
            hr = MapHealthReport.objects.all().filter(
                map_configuration=retrieve(country, organization_type_id),
                at_when__year=old_date.year,
                at_when__month=old_date.month,
                at_when__day=old_date.day,
            ).first()
            if not hr:
                hr = MapHealthReport()
            hr.map_configuration = retrieve(country, organization_type_id)
            hr.at_when = old_date
            hr.percentage_up_to_date = report['percentage_up_to_date']
            hr.percentage_out_of_date = report['percentage_out_of_date']
            hr.outdate_period_in_hours = report['outdate_period_in_hours']
            hr.detailed_report = report
            hr.save()


def get_outdated_ratings(organizations: List[Organization]) -> List[Dict[str, Any]]:
    total_outdated = []

    for organization in organizations:
        # log.debug(f"Creating health report of {organization} at {old_date}.")
        latest_report = get_latest_report_of_organization(organization, datetime.now(pytz.utc))
        if not latest_report:
            continue

        ratings_outdated, ratings_good = split_ratings_between_good_and_bad(latest_report, OUTDATED_HOURS)
        total_outdated += ratings_outdated

    return total_outdated


def get_latest_report_of_organization(organization, at_when):
    return OrganizationReport.objects.all().filter(
        organization=organization,
        at_when__lte=at_when
    ).order_by('-at_when').first()


def split_ratings_between_good_and_bad(report: OrganizationReport, hours: int = OUTDATED_HOURS) -> Tuple[
        List[Dict[str, Any]], List[Dict[str, Any]]]:
    now = datetime.now(pytz.utc)
    a_while_ago = now - timedelta(hours=hours)
    infractions = []
    good = []
    for url in report.calculation['organization']['urls']:
        # endpoint ratings
        for endpoint in url['endpoints']:
            for rating in endpoint['ratings']:
                # make sure to be able to figure out what url is causing it, so it's easier to reschedule
                # a scan for this finding.
                rating['url'] = url['url']
                if dateutil.parser.isoparse(rating['last_scan']) < a_while_ago:
                    infractions.append(rating)
                else:
                    good.append(rating)
        # url ratings (dnssec etc)
        for rating in url['ratings']:
            # make sure to be able to figure out what url is causing it, so it's easier to reschedule
            # a scan for this finding.
            rating['url'] = url['url']
            if dateutil.parser.isoparse(rating['last_scan']) < a_while_ago:
                infractions.append(rating)
            else:
                good.append(rating)
    return infractions, good


def get_lastest_map_health_data(country: str = "NL", organization_type: str = "municipality") -> Dict[str, Any]:
    map_configuration = Configuration.objects.all().filter(
        country=get_country(country),
        organization_type=get_organization_type(organization_type)
    ).first()
    mh = MapHealthReport.objects.all().filter(map_configuration=map_configuration).latest('at_when')
    return mh.detailed_report


def create_health_report(outdated: List, good: List, published_scan_types):
    """
    Returns:
        {
            'outdate_period_in_hours': 72,
            'percentage_up_to_date': 42.42,
            'percentage_out_of_date': 57.58,
            'per_scan': [
                {
                    'scan_type': ...,
                    'percentage_up_to_date': 42.42,
                    'percentage_out_of_date': 57.58,
                },
                ...
            ]

        }

    """
    # only include published metrics:
    outdated = [item for item in outdated if item.get('scan_type', 'unknown') in published_scan_types]
    good = [item for item in good if item.get('scan_type', 'unknown') in published_scan_types]
    nr_total = len(good) + len(outdated)
    nr_good = len(good)
    nr_outdated = len(outdated)
    if not nr_total:
        return {
            'outdate_period_in_hours': OUTDATED_HOURS,
            'percentage_up_to_date': 0,
            'percentage_out_of_date': 0,
            'amount_up_to_date': 0,
            'amount_out_of_date': 0,
            'per_scan': []
        }
    report = {
        'outdate_period_in_hours': OUTDATED_HOURS,
        'percentage_up_to_date': round(nr_good / nr_total * 100, 2),
        'percentage_out_of_date': round(nr_outdated / nr_total * 100, 2),
        'amount_up_to_date': nr_good,
        'amount_out_of_date': nr_outdated,
        'per_scan': []
    }
    failures_per_scan_type = defaultdict(dict)
    for outdate in outdated:
        if not failures_per_scan_type[outdate.get('scan_type', 'unknown')]:
            failures_per_scan_type[outdate.get('scan_type', 'unknown')] = {'total': 0, 'outdated': 0, 'good': 0}
        failures_per_scan_type[outdate.get('scan_type', 'unknown')]['total'] += 1
        failures_per_scan_type[outdate.get('scan_type', 'unknown')]['outdated'] += 1
    for outdate in good:
        if not failures_per_scan_type[outdate.get('scan_type', 'unknown')]:
            failures_per_scan_type[outdate.get('scan_type', 'unknown')] = {'total': 0, 'outdated': 0, 'good': 0}
        failures_per_scan_type[outdate.get('scan_type', 'unknown')]['total'] += 1
        failures_per_scan_type[outdate.get('scan_type', 'unknown')]['good'] += 1
    for key in failures_per_scan_type.keys():
        per_scan_good = failures_per_scan_type[key]['good']
        per_scan_outdated = failures_per_scan_type[key]['outdated']
        per_scan_total = per_scan_good + per_scan_outdated
        if not per_scan_total:
            continue
        report['per_scan'].append({
            'scan_type': key,
            'percentage_up_to_date': round(per_scan_good / per_scan_total * 100, 2),
            'percentage_out_of_date': round(per_scan_outdated / per_scan_total * 100, 2),
            'amount_up_to_date': per_scan_good,
            'amount_out_of_date': per_scan_outdated,
        })
    return report
