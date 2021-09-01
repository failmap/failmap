import os

from django.utils import timezone

from websecmap.map.models import OrganizationReport
from websecmap.reporting.diskreport import (
    sync_reports_from_db_to_disk,
    get_original_storage_location,
    read_json_from_gzip,
)
from websecmap.scanners.tests.test_plannedscan import create_organization


def test_report_syncing(db):

    stored_data = {"yolo": "swag"}

    # setup creates a report for an organization
    organization = create_organization()
    organizationreport = OrganizationReport()
    organizationreport.calculation = stored_data
    organizationreport.organization = organization
    organizationreport.at_when = timezone.now()
    organizationreport.save()

    # saves the report to disk and removes calculations from the database
    sync_reports_from_db_to_disk()

    # the file was created, the report is retrievable
    first_report = OrganizationReport.objects.first()
    assert first_report.calculation is None
    assert os.path.isfile(f"{get_original_storage_location()}{first_report.id}.gson")
    assert read_json_from_gzip(f"{get_original_storage_location()}{first_report.id}.gson") == stored_data
