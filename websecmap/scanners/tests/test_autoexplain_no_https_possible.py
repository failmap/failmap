from datetime import datetime, timezone

from websecmap.scanners.models import EndpointGenericScan, PlannedScan
from websecmap.scanners.scanner.autoexplain_no_https_possible import plan_scan, scan
from websecmap.scanners.tests.test_plannedscan import (
    create_endpoint,
    create_endpoint_scan,
    create_organization,
    create_url,
    link_url_to_organization,
)


def test_autoexplain_no_https_possible(db, default_scan_metadata, default_policy):
    # Three different endpoints, one will be explained because it has the pki subdomain and a 1000 score.
    o = create_organization("Test")
    u1 = create_url("pki.example.com")
    link_url_to_organization(u1, o)
    e1 = create_endpoint(u1, 4, "https", 443)
    e2 = create_endpoint(u1, 6, "https", 443)
    es1 = create_endpoint_scan(
        e1, "plain_http", "no_https_redirect_and_no_https_on_standard_port", datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    es2 = create_endpoint_scan(e2, "plain_http", "redirecting_properly", datetime(2020, 1, 1, tzinfo=timezone.utc))

    u2 = create_url("sip.example2.com")
    link_url_to_organization(u2, o)
    e3 = create_endpoint(u2, 4, "https", 443)
    es3 = create_endpoint_scan(
        e3, "plain_http", "no_https_redirect_and_no_https_on_standard_port", datetime(2020, 1, 1, tzinfo=timezone.utc)
    )

    plan_scan()

    assert PlannedScan.objects.all().count() == 1
    first_planned_scan = PlannedScan.objects.all().first()
    assert first_planned_scan.url == u1

    scan(es1.id)
    scan(es2.id)
    scan(es3.id)

    egs = EndpointGenericScan.objects.all().filter(pk=es1.pk).first()
    assert egs.comply_or_explain_is_explained is True

    egs = EndpointGenericScan.objects.all().filter(pk=es2.pk).first()
    assert egs.comply_or_explain_is_explained is False

    egs = EndpointGenericScan.objects.all().filter(pk=es3.pk).first()
    assert egs.comply_or_explain_is_explained is False
