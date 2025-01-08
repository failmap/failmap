from datetime import datetime, timedelta, timezone
from freezegun import freeze_time

from websecmap.organizations.models import Url
from websecmap.scanners.models import UrlGenericScan, Endpoint, EndpointGenericScan
from websecmap.scanners.servicelevel_monitoring import metric_to_statsd, export_metric_metadata_to_statsd


def test_metric_to_statsd():

    # this test will fail at exactly the interval between before midnight and now probably. So freeze time:
    with freeze_time("2020-01-01 12:00"):

        logged = metric_to_statsd(
            metric_type="web_privacy_cookies",
            rating="web_privacy_cookies_neutral",
            rating_determined_on=datetime.now(timezone.utc) - timedelta(days=4),
            last_scan_moment=datetime.now(timezone.utc) - timedelta(days=1),
            kind="endpoint",
        )

        assert logged == {
            "type": "web_privacy_cookies",
            "rating": "web_privacy_cookies_neutral",
            "rating_determined_on_days": 4,
            "last_scan_moment_days": 1,
            "kind": "endpoint",
        }

        logged = metric_to_statsd(
            metric_type="web_privacy_cookies",
            rating="web_privacy_cookies_neutral",
            rating_determined_on=datetime.now(timezone.utc) - timedelta(days=900),
            last_scan_moment=datetime.now(timezone.utc) - timedelta(days=900),
            kind="endpoint",
        )

        # limit to max 60 days.
        assert logged == {
            "type": "web_privacy_cookies",
            "rating": "web_privacy_cookies_neutral",
            "rating_determined_on_days": 60,
            "last_scan_moment_days": 60,
            "kind": "endpoint",
        }


def test_export_metric_metadata_to_statsd(db, caplog):
    now = datetime.now(timezone.utc)

    # make sure it at least does not crash:
    export_metric_metadata_to_statsd()

    # then make sure the rest of the logic doesn't crash...
    url = Url.objects.all().create(url="test.nl", not_resolvable=False, is_dead=False, created_on=now)
    UrlGenericScan.objects.create(
        type="urltest", rating="A", url=url, is_the_latest_scan=True, rating_determined_on=now, last_scan_moment=now
    )

    # a standard HTTPS endpoint
    ep = Endpoint.objects.all().create(url=url, protocol="https", port="443", ip_version=4, is_dead=False)

    EndpointGenericScan.objects.all().create(
        endpoint=ep,
        type="eptest",
        rating="A+",
        rating_determined_on=now,
        last_scan_moment=now,
        comply_or_explain_is_explained=False,
        is_the_latest_scan=True,
    )

    export_metric_metadata_to_statsd()

    assert "urltest - A" in caplog.text
    assert "eptest - A+" in caplog.text
