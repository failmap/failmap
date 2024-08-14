from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from typing import Optional

from django.db.models import QuerySet

from websecmap.celery import app
from websecmap.organizations.models import Url, OrganizationType
from websecmap.reporting.severity import get_severity
from websecmap.scanners.models import Endpoint, EndpointGenericScan, RatingOptions, ScanType, UrlGenericScan


@app.task(queue="storage", ignore_result=True)
def calculate_progress_and_regression():
    # metrics = ScanType.objects.all().filter(include_in_report=True, show_in_frontend=True)

    # now only run on things that didn't die, which misses a lot probably. Database really neads a cleanup...
    eps = Endpoint.objects.all().filter(is_dead=False, url__is_dead=False, url__not_resolvable=False)
    for endpoint in eps:
        # this might be gruesomely slow... and better just to still iterate all available metrics with some heuristcs
        metrics = EndpointGenericScan.objects.all().filter(endpoint=endpoint).values_list("type", flat=True).distinct()
        for metric in metrics:
            calculate_for_metric_on_endpoint.s(endpoint.id, metric).apply_async()

    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False)
    for url in urls:
        metrics = UrlGenericScan.objects.all().filter(url=url).values_list("type", flat=True).distinct()
        for metric in metrics:
            calculate_for_metric_on_url.s(url.id, metric).apply_async()


def prr_impact(severity, previous_value: Optional[str]) -> Optional[str]:
    # this differs from the usual get_impact... lets make it prr_impact
    allowed = ["high", "medium", "low", "ok", None]

    # all cases of errors, not testable and whatever: this will pass of the last known correct impact to the next
    # scan so several errors can be there and we can still see if there is a progression or regression...
    if previous_value not in allowed:
        previous_value = None

    if severity["is_explained"]:
        # done: if something is explained, was it always ok? Probably... -> and this is an improvement then?
        # what about those metrics that are explained over and over again? -> those should be cleaned up and
        # the one metric that is wrong should then be okayed...
        return "ok"

    # all cases where there is no severity that we can rate, return the previous value, which may also be none
    if not any([severity["high"], severity["medium"], severity["low"], severity["ok"]]):
        return previous_value

    return "high" if severity["high"] else "medium" if severity["medium"] else "low" if severity["low"] else "ok"


@app.task(queue="storage", ignore_result=True)
def calculate_for_metric_on_endpoint(endpoint_id: int, metric_name: str):
    endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    if not endpoint:
        return

    scans = EndpointGenericScan.objects.filter(endpoint=endpoint, type=metric_name).order_by("id")
    calculate_progression_and_regression_on_scans(scans)


@app.task(queue="storage", ignore_result=True)
def calculate_for_metric_on_url(url_id: int, metric_name: str):
    url = Url.objects.all().filter(id=url_id).first()
    if not url:
        return

    scans = UrlGenericScan.objects.filter(url=url, type=metric_name).order_by("id")
    calculate_progression_and_regression_on_scans(scans)


def calculate_progression_and_regression_on_scans(scans: QuerySet) -> None:
    # the first scan is the baseline, it's not possible to calculate pro/regression without it
    if not scans.exists():
        return

    # retrieve the current policy from cache, we need that so to understand what the metrics actually mean
    # this is already done right in reporting...

    # what are the error_in_test etc? add those impacts next... so we can compare in outages and scan errors.
    impact_order = ["ok", "low", "medium", "high"]

    baseline = scans[0]
    previous_impact = prr_impact(get_severity(baseline), None)
    for scan in scans[1:]:
        current_impact = prr_impact(get_severity(scan), previous_impact)
        # log.debug("Current impact: %s, Previous impact: %s", current_impact, previous_impact)
        if current_impact and previous_impact:
            # previous impacts can only be None on the first measurement (until it is not None anymore) as the
            # first series of things can be errors. For that scenario there is never a progression or regression.
            if impact_order.index(current_impact) < impact_order.index(previous_impact):
                # if this is better:
                scan.prr_is_progress = True

            if impact_order.index(current_impact) > impact_order.index(previous_impact):
                # if this is worse:
                scan.prr_is_regression = True

            # in any case save what we are coming from:
            # todo: fix uppercase and make all of this lowercase.
            scan.prr_was_previously = RatingOptions[previous_impact.upper()].value

            # log.debug("+: %s, -:%s, prev: %s",  scan.prr_is_progress,  scan.prr_is_regression,
            # scan.prr_was_previously)
        previous_impact = current_impact

        # don't interfere with currently running database operations:
        scan.save(update_fields=["prr_is_progress", "prr_is_regression", "prr_was_previously"])

        # todo: does this skip some records and will those keep their old values if we run this again over time?


def demo_progress_per_metric_per_layer_per_month():
    metrics = ScanType.objects.all().filter(include_in_report=True, show_in_frontend=True)

    oldest = EndpointGenericScan.objects.all().order_by("id").first().rating_determined_on
    oldest.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today = datetime.now(timezone.utc)
    pointer = oldest

    layers = OrganizationType.objects.all()

    while pointer < today:
        print(f"Progress in month {pointer.strftime('%Y-%m')}")
        for layer in layers:
            # this is just a demo where we can see some of the recorded progress.
            for metric in metrics:
                progress = EndpointGenericScan.objects.filter(
                    type=metric.name,
                    prr_is_progress=True,
                    rating_determined_on__month=pointer.month,
                    rating_determined_on__year=pointer.year,
                    endpoint__url__organization__layers=layer,
                ).count()
                regression = EndpointGenericScan.objects.filter(
                    type=metric.name,
                    prr_is_regression=True,
                    rating_determined_on__month=pointer.month,
                    rating_determined_on__year=pointer.year,
                    endpoint__url__organization__layers=layer,
                ).count()
                if progress or regression:
                    print(f"- {layer.name}: {metric.name}: {progress} progress, {regression} regression")

        pointer += relativedelta(months=1)


def reset_progress():
    EndpointGenericScan.objects.update(
        prr_is_progress=False, prr_is_regression=False, prr_was_previously=RatingOptions.OK
    )
