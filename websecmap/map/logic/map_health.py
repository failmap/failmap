from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import dateutil.parser
import pytz

from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration, MapHealthReport, OrganizationReport
from websecmap.organizations.models import Organization

OUTDATED_HOURS = 24 * 7

"""
Retrieves all reports of a map, and will determine the health of those reports to a single percentage.

Everything before OUTDATED_HOURS is wrong. So with 200 OUTDATED_HOURS of 400 total, the grade is 50%.
If there are no reports, the grade is 0%.

This grade gets stored inside a model related to a certain map, so the metric can be retrieved over time.
"""


@app.task(queue="storage")
def update_map_health_reports(published_scan_types):
    map_configurations = Configuration.objects.all()
    for map_configuration in map_configurations:
        total_outdated = []
        total_good = []
        organizations_on_map = Organization.objects.all().filter(
            country=map_configuration.country, type=map_configuration.organization_type)
        for organization in organizations_on_map:
            print(f"Creating health report of {organization}")
            latest_report = OrganizationReport.objects.all().filter(organization=organization).last()
            if not latest_report:
                continue
            ratings_outdated, ratings_good = split_ratings_between_good_and_bad(latest_report, OUTDATED_HOURS)
            total_outdated += ratings_outdated
            total_good += ratings_good
        report = \
            create_health_report(total_outdated, total_good, published_scan_types)
        # Update reports of a certain day. For example when the report for a single day is re-generated.
        now = datetime.now(pytz.utc)
        hr = MapHealthReport.objects.all().filter(
            map_configuration=map_configuration,
            at_when__year=now.year,
            at_when__month=now.month,
            at_when__day=now.day,
        ).first()
        if not hr:
            hr = MapHealthReport()
        hr.map_configuration = map_configuration
        hr.at_when = datetime.now(pytz.utc)
        hr.percentage_up_to_date = report['percentage_up_to_date']
        hr.percentage_out_of_date = report['percentage_out_of_date']
        hr.outdate_period_in_hours = report['outdate_period_in_hours']
        hr.detailed_report = report
        hr.save()


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
                if dateutil.parser.isoparse(rating['last_scan']) < a_while_ago:
                    infractions.append(rating)
                else:
                    good.append(rating)
        # url ratings (dnssec etc)
        for rating in url['ratings']:
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
