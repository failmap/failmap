from websecmap.celery import app
from websecmap.reporting.severity import get_severity
from websecmap.scanners.models import Endpoint, EndpointGenericScan, ScanType, RatingOptions


@app.task(queue="storage", ignore_result=True)
def calculate_progress_and_regression():
    # todo: optimize: not all metrics apply to all types of endpoints... Mostly not.
    metrics = ScanType.objects.all().filter(include_in_report=True, show_in_frontend=True)

    # now only run on things that didn't die, which misses a lot probably. Database really neads a cleanup...
    eps = Endpoint.objects.all().filter(is_dead=False, url__is_dead=False, url__not_resolvable=False)
    for endpoint in eps:
        for metric in metrics:
            calculate_for_metric_on_endpoint.s(endpoint.id, metric.name).apply_async()


def get_impact(severity):
    if severity["is_explained"]:
        # todo: if something is explained, was it always ok? Probably...
        return "ok"
    return "high" if severity["high"] else "medium" if severity["medium"] else "low" if severity["low"] else "ok"


@app.task(queue="storage", ignore_result=True)
def calculate_for_metric_on_endpoint(endpoint_id: int, metric_name: str):
    # todo: the current implementation does not work with temporary errors. It will see those as OK...

    endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    if not endpoint:
        return

    scans = EndpointGenericScan.objects.filter(endpoint=endpoint, type=metric_name).order_by("id")

    # the first scan is the baseline, it's not possible to calculate pro/regression without it
    if not scans.exists():
        return

    # retrieve the current policy from cache, we need that so to understand what the metrics actually mean
    # this is already done right in reporting...

    # todo: the other get_impact is not a great method as it works with "good" and doesn't work well with explanations
    #  and doesn't work well with errors. And doesn't work well at all i guess...

    # what are the error_in_test etc? add those impacts next... so we can compare in outages and scan errors.
    impact_order = ["ok", "low", "medium", "high"]

    baseline = scans[0]
    previous_impact = get_impact(get_severity(baseline))
    for scan in scans[1:]:
        current_impact = get_impact(get_severity(scan))

        if impact_order.index(current_impact) < impact_order.index(previous_impact):
            # if this is better:
            scan.prr_is_progress = True

        if impact_order.index(current_impact) > impact_order.index(previous_impact):
            # if this is worse:
            scan.prr_is_regression = True

        # in any case save what we are coming from:
        # todo: fix uppercase and make all of this lowercase.
        scan.prr_was_previously = RatingOptions[previous_impact.upper()].value

        # don't interfere with currently running database operations:
        scan.save(update_fields=["prr_is_progress", "prr_is_regression", "prr_was_previously"])


def demo_progress_per_metric_per_layer_per_month():
    # this is just a demo where we can see some of the recorded progress.
    ...


def reset_progress():
    EndpointGenericScan.objects.update(
        prr_is_progress=False, prr_is_regression=False, prr_was_previously=RatingOptions.OK
    )
