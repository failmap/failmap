import logging

from celery import group
from django.utils import timezone

from failmap.celery import Task, app
from failmap.organizations.models import Url
from failmap.scanners.scanner.scanner import url_filters
from failmap.scanners.tasks import crawl_tasks, explore_tasks, scan_tasks

log = logging.getLogger(__package__)


@app.task(queue='storage')
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Multi-stage onboarding."""

    """
    This onboarder has multiple stages. The main reason for this is that the original plan failed: endpoints where
    discovered but the next task hanged. This is extensively documented here:
    https://github.com/celery/celery/issues/4681

    Therefore this onboarding task creates different sets of tasks per stage per url.

    Stage:
    V ""
    V endpoint_discovery    endpoints are discovered on the url
    V endpoint_finished     done, ready for next stage
    V scans_running         running a series of scans on the endpoints
    V scans_finished        done, ready for next stage
    V crawl_started         trying to find more endpoints (via DNS)
    V crawl_finished        IMPLICIT! Last step will not be saved.
    - onboarded             onboarding completed

    Todo: date the last step was set. So we can find processes that failed and retry.
    Todo: run this every minute.
    """

    # Resetting the outdated onboarding has a risk: if the queue takes longer than the onboarding tasks to finish the
    # tasks will be performed multiple time. This can grow fast and large. Therefore a very large time has been taken
    # to reset onboarding of tasks. Normally onboarding should be one within 5 minutes. We'll reset after 7 days.
    reset_expired_onboards()

    urls = Url.objects.all().filter(onboarded=False)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    # todo: filter out the scans that failed / took too long and try again.

    log.info("Found %s urls to create tasks for." % len(urls))

    tasks = []
    for url in urls:
        log.info("Url %s is at onboarding_stage: %s", url, url.onboarding_stage)

        # you will see this happen per worker-size (so for example per 20 things)
        if not url.onboarding_stage:  # While developing: or url.onboarding_stage == "endpoint_discovery":
            log.info("Exploring on: %s", url)
            # Of course this will still fail as the bug aforementioned was not fixed. have to rewrite that.
            tasks.append(update_stage.si(url, "endpoint_discovery")
                         | explore_tasks(url)
                         | update_stage.si(url, "endpoint_finished"))

        elif url.onboarding_stage in ["endpoint_finished"]:  # dev: , "scans_running"
            log.info("Scanning on: %s", url)
            tasks.append(update_stage.si(url, "scans_running")
                         | scan_tasks(url)
                         | update_stage.si(url, "scans_finished"))

        elif url.onboarding_stage == "scans_finished":
            log.info("Crawling on: %s", url)
            tasks.append(update_stage.si(url, "endpoint_finished")
                         | crawl_tasks(url)
                         | finish_onboarding.si(url))
        else:
            # Do nothing when wheels are set in motion or an unknown state is encountered.
            pass

    log.info("Created %s tasks to be performed." % len(tasks))
    task = group(tasks)

    # log.info("Task:")
    # log.info(task)

    return task


def reset_expired_onboards():
    from datetime import datetime, timedelta
    import pytz

    expired = Url.objects.all().filter(onboarding_stage_set_on__lte=datetime.now(pytz.utc) - timedelta(days=7))

    for url in expired:
        # set the task a step back.
        # retry endpoint discovery if that didn't finish.
        if url.onboarding_stage == "endpoint_discovery":
            url.onboarding_stage = ""

        # retry scanning after discovery of endpoints
        if url.onboarding_stage == "scans_running":
            url.onboarding_stage = "endpoint_finished"

        # retry crawling after scans are finished
        if url.onboarding_stage == "crawl_started":
            url.onboarding_stage = "scans_finished"

        url.save()


@app.task(queue='storage')
def finish_onboarding(url):
    log.info("Finishing onboarding of %s", url)
    url.onboarded = True
    url.onboarded_on = timezone.now()
    url.onboarding_stage = "onboarded"
    url.save(update_fields=['onboarded_on', 'onboarded', 'onboarding_stage'])
    return True


@app.task(queue='storage')
def update_stage(url, stage=""):
    log.info("Updating onboarding_stage of %s from %s to %s", url, url.onboarding_stage, stage)
    url.onboarding_stage = stage
    url.save(update_fields=['onboarding_stage'])
    return True