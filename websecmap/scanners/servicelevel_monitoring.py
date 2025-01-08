""" Export metric metadata to statsd, so we can see if all metrics are being updated within our service level window """

from datetime import datetime, timezone

from statshog.defaults.django import statsd

from websecmap.celery import app
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

import logging

log = logging.getLogger(__name__)


@app.task(queue="storage", ignore_result=True)
def export_metric_metadata_to_statsd():
    # plan this every 10 minutes... or once per hour
    endpoint_metrics = (
        EndpointGenericScan.objects.all()
        .filter(
            is_the_latest_scan=True,
            endpoint__is_dead=False,
            endpoint__url__is_dead=False,
            endpoint__url__not_resolvable=False,
        )
        .only("id", "type", "rating", "rating_determined_on", "last_scan_moment")
    )
    dump_metrics(endpoint_metrics, "endpoint")

    url_metrics = (
        UrlGenericScan.objects.all()
        .filter(url__is_dead=False, url__not_resolvable=False, is_the_latest_scan=True)
        .only("id", "type", "rating", "rating_determined_on", "last_scan_moment")
    )
    dump_metrics(url_metrics, "url")


def dump_metrics(metrics, kind):
    # instead of converting the queryset to lists and then concatenating these lists, just go over the list once.
    # the "kind" helps explaining the difference in amounts of metrics. there are many more endpoints than urls...
    for metric in metrics:
        log.debug("Exporting metric metadata to statsd: %s - %s", metric.type, metric.rating)
        # direct call, no celery, as statsd is cheap...
        metric_to_statsd(metric.type, metric.rating, metric.last_scan_moment, metric.rating_determined_on, kind)


def metric_to_statsd(metric_type, rating, last_scan_moment, rating_determined_on, kind):
    """
    The dashboard needed:

    Today:
    metric: dnssec
    last_scan_moment_days_ago 0 = 100
    last_scan_moment_days_ago 1 = 200
    last_scan_moment_days_ago 2 = 5100
    last_scan_moment_days_ago 3 = 200
    last_scan_moment_days_ago 122 = 100

    # -> so an outlier or outdated metric (over two months) becomes clear

    And the other dashboard:
    Today:
    metric: dnssec
    rating_determined_on_days_ago 0 = 0
    rating_determined_on_days_ago 1 = 1
    rating_determined_on_days_ago 2 = 0
    rating_determined_on_days_ago 5 = 200

    # -> this should have pretty high numbers in the past, if there are new numbers probably the metric / evidence
    # or other data is not cleaned up / reduced correctly.

    # this also stores old records and things out of sight of the scanmanager. The scanmanager only sees things that are
    current, not polluted or old or wasted data that is here.

    """
    now = datetime.now(timezone.utc)

    # limit to 60 days to not create too many dimensions... a lot of determined on will/should be older than 60.
    last_scan_moment_days_ago = min((now - last_scan_moment).days, 60)
    rating_determined_on_days_ago = min((now - rating_determined_on).days, 60)

    tags = {
        "last_scan_moment_days": last_scan_moment_days_ago,
        "rating_determined_on_days": rating_determined_on_days_ago,
        "type": metric_type,
        "rating": rating,
        "kind": kind,
    }

    # here you know the amount of metrics. When sending this data in once a day you know how many metrics there are.
    statsd.incr("scan_result_days_ago_count", 1, tags=tags)

    # for testing purposes, this will normally be ignored.
    return tags
