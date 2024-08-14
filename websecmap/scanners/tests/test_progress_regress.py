from datetime import datetime, timezone, timedelta

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

    # running this multiple times should not cause changes...
    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")
    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")
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


def test_complex_scenario(db, default_policy, default_scan_metadata):
    # This scenario has several ups and downs including several error scenario's which should not be impacting the
    # progression or regression over time.

    url = create_url("example.com")
    ep = create_endpoint(url, 4, "https", 443)
    # 2 progressions and two regressions
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc) + timedelta(days=1))
    # progress 1, with several identical metrics...
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc) + timedelta(days=2))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc) + timedelta(days=3))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc) + timedelta(days=4))
    # regress 1:
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc) + timedelta(days=5))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc) + timedelta(days=6))
    # progress 2:
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc) + timedelta(days=7))
    # regress 2:
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc) + timedelta(days=8))

    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")

    assert EndpointGenericScan.objects.all().filter(prr_is_regression=True).count() == 2
    assert EndpointGenericScan.objects.all().filter(prr_is_progress=True).count() == 2


def test_complex_error_scenario(db, default_policy, default_scan_metadata):
    # This scenario has several ups and downs including several error scenario's which should not be impacting the
    # progression or regression over time.

    url = create_url("example.com")
    ep = create_endpoint(url, 4, "https", 443)
    # 2 progressions and two regressions
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))

    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")

    # this is one progression
    assert EndpointGenericScan.objects.all().filter(prr_is_progress=True).count() == 1

    # and now regress from errors and progress again:
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))

    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")

    assert EndpointGenericScan.objects.all().filter(prr_is_regression=True).count() == 2
    assert EndpointGenericScan.objects.all().filter(prr_is_progress=True).count() == 2


def test_starting_with_an_error(db, default_policy, default_scan_metadata):
    url = create_url("example.com")
    ep = create_endpoint(url, 4, "https", 443)

    # let's start with an error, this should have no impact as well, the first A is just the first measurement and
    # not an improvement.
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "scan_error", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
    create_endpoint_scan(ep, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))

    calculate_for_metric_on_endpoint(ep.id, "tls_qualys_encryption_quality")

    # this is one progression
    assert EndpointGenericScan.objects.all().filter(prr_is_progress=True).count() == 1
    assert EndpointGenericScan.objects.all().filter(prr_is_regression=True).count() == 0
