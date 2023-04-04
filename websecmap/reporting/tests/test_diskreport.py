import os
from datetime import datetime, timezone

from websecmap.map.models import OrganizationReport
from websecmap.reporting.diskreport import (
    _read_json_from_gzip,
    location_on_disk,
    retrieve_report,
    sync_reports_from_db_to_disk,
)
from websecmap.scanners.tests.test_plannedscan import create_organization


def test_report_syncing(db):

    stored_data = {"yolo": "swag"}

    # setup creates a report for an organization
    organization = create_organization()
    organizationreport = OrganizationReport()
    organizationreport.calculation = stored_data
    organizationreport.organization = organization
    organizationreport.at_when = datetime.now(timezone.utc)
    organizationreport.save()

    # saves the report to disk and removes calculations from the database
    sync_reports_from_db_to_disk()

    # the file was created, the report is retrievable
    first_report = OrganizationReport.objects.get(id=organizationreport.id)
    assert first_report.calculation is None
    assert os.path.isfile(location_on_disk(first_report.id, "OrganizationReport"))
    assert retrieve_report(first_report.id, "OrganizationReport") == stored_data
    assert _read_json_from_gzip(location_on_disk(first_report.id, "OrganizationReport")) == stored_data
