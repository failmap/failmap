from datetime import datetime, timezone

from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.progress_regress_results import (
    calculate_for_metric_on_endpoint,
    calculate_progress_and_regression,
)
from websecmap.scanners.tests.test_plannedscan import create_url, create_endpoint, create_endpoint_scan


def test_some_progression(db, default_policy, default_scan_metadata):
    # simplest example: have an old scan which is bad, then a new scan which is good. Now we have 1 point :)

    url = create_url("example.com")
    ep = create_endpoint(url, 4, "https", 443)
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))

    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")

    assert EndpointGenericScan.objects.all().filter(prr_is_regression=True).count() == 0
    assert EndpointGenericScan.objects.all().filter(prr_is_progress=True).count() == 1


def test_progression_loop(db, default_policy, default_scan_metadata):
    # same test as the previous one, but make sure the method is called on all metrics on all endpoints.
    url = create_url("example.com")
    ep = create_endpoint(url, 4, "https", 443)
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))

    # make sure the loop doesn't crash at least
    calculate_progress_and_regression()
