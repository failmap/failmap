from websecmap.map.models import OrganizationReport
from websecmap.map.report import create_organization_reports_now
from websecmap.organizations.models import Organization
from websecmap.reporting.report import add_ultimate_report
from websecmap.scanners.models import EndpointGenericScan


def test_create_ultimate_report(db, default_scan_metadata, default_policy):
    # this matches the scan types from the db while there is no referential integrity
    # this integrity is also not desired, as you might want to collect metrics first and then
    # determine what to use them for.

    # Todo: not all metrics are ending up in one report, probably because the reporting part might just take one
    # metric

    # this should run without crashes
    add_ultimate_report()
    create_organization_reports_now([Organization.objects.all().first().id])

    # make sure nobody trashed the database
    assert EndpointGenericScan.objects.all().count() > 400
    assert OrganizationReport.objects.all().count() == 1
