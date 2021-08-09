import logging
from datetime import datetime, timedelta
from typing import List

import pytz
from celery import group
from django.utils import timezone

from websecmap.celery import Task, app
from websecmap.map.report import update_report_tasks
from websecmap.organizations.models import Url
from websecmap.scanners.scanner.__init__ import q_configurations_to_scan, url_filters
from websecmap.scanners.tasks import crawl_tasks, explore_tasks, scan_tasks

log = logging.getLogger(__package__)


def in_chunks(my_list, n):
    # Example: chunks = list(chunks(urls, 25))
    # creates list of lists containing N items.
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), n):
        # Create an index range for l of n items:
        yield my_list[i : i + n]


def compose_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
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
    V crawling              trying to find more endpoints (via DNS)
    V crawl_finished        IMPLICIT! Last step will not be saved.
    - onboarded             onboarding completed

    Todo: date the last step was set. So we can find processes that failed and retry.
    Todo: run this every minute.
    """

    # Resetting the outdated onboarding has a risk: if the queue takes longer than the onboarding tasks to finish the
    # tasks will be performed multiple time. This can grow fast and large. Therefore a very large time has been taken
    # to reset onboarding of tasks. Normally onboarding should be one within 5 minutes. We'll reset after 7 days.
    reset_expired_onboards()

    default_filter = {"onboarded": "False"}
    urls_filter = {**urls_filter, **default_filter}

    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    log.info("Found %s urls to create tasks for." % len(urls))

    # it's impossible to set the first stage "endpoint_discovery" in a task, as the task might take an hour
    # to complete (depending of how much work is in the queue. Could be days. So therefore to trigger the first
    # stage and not to re-submit the url for onboarding (again and again and again) the first stage is set in
    # this routine for each of the steps.

    # some urls can be returned a number of times if they are shared amongs organizations, this reduces that:
    # note that mysql and sqlite dont support DISTINCT ON.
    urls = list(set(urls))

    endpoint_discovery_urls = []
    scans_running_urls: List[int] = []
    crawling_urls = []

    tasks = []
    for url in urls:
        log.info("Url %s is at onboarding_stage: %s", url, url.onboarding_stage)

        # you will see this happen per worker-size (so for example per 20 things)
        if not url.onboarding_stage:  # While developing: or url.onboarding_stage == "endpoint_discovery":
            log.info("Exploring on: %s", url)
            update_stage([url], "endpoint_discovery")
            endpoint_discovery_urls.append(url)

        elif url.onboarding_stage in ["endpoint_finished"]:  # dev: , "scans_running"
            log.info("Scanning on: %s", url)
            update_stage([url], "scans_running")
            scans_running_urls.append(url.pk)

        elif url.onboarding_stage == "scans_finished":
            log.info("Crawling on: %s", url)
            update_stage([url], "crawling")
            crawling_urls.append(url)

        else:
            # Do nothing when wheels are set in motion or an unknown state is encountered.
            pass

    for url in endpoint_discovery_urls:
        tasks.append(explore_tasks(url) | update_stage.si([url], "endpoint_finished"))

    chunks = in_chunks(scans_running_urls, 25)
    for chunk in chunks:
        tasks.append(scan_tasks(chunk) | update_report_tasks(chunk) | update_stage.si(chunk, "scans_finished"))

    for url in crawling_urls:
        tasks.append(crawl_tasks(url) | finish_onboarding.si(url))

    log.info("Created %s tasks to be performed." % len(tasks))
    task = group(tasks)

    # log.info("Task:")
    # log.info(task)

    return task


def reset_expired_onboards():
    # If the queues don't finish in 7 days, you have a problem somewhere. This will add to that problem by adding
    # EVEN MORE tasks to the queue. So an unmanaged system will run out of space somewhere sometime :)
    expired = list(Url.objects.all().filter(onboarding_stage_set_on__lte=datetime.now(pytz.utc) - timedelta(days=7)))

    # some older tasks might never have an onboarding stage due to a bug. add those too:
    expired += list(Url.objects.all().filter(onboarding_stage_set_on__isnull=True))

    for url in expired:
        reset_onboarding_status(url)


def reset_onboarding_status(url):
    # set the task a step back.
    # retry endpoint discovery if that didn't finish.
    if url.onboarding_stage == "endpoint_discovery":
        url.onboarding_stage = ""

    # retry scanning after discovery of endpoints
    if url.onboarding_stage == "scans_running":
        url.onboarding_stage = "endpoint_finished"

    # retry crawling after scans are finished
    if url.onboarding_stage == "crawling":
        url.onboarding_stage = "scans_finished"

    url.save()


def forward_onboarding_status(url):
    # set the task a step back.
    # retry endpoint discovery if that didn't finish.
    if url.onboarding_stage == "endpoint_discovery":
        url.onboarding_stage = "endpoint_finished"

    # retry scanning after discovery of endpoints
    if url.onboarding_stage == "scans_running":
        url.onboarding_stage = "scans_finished"

    # retry crawling after scans are finished
    if url.onboarding_stage == "crawling":
        url.onboarded = True
        url.onboarded_on = timezone.now()
        url.onboarding_stage = "onboarded"

    url.save()


@app.task(queue="storage")
def finish_onboarding(url):
    log.info("Finishing onboarding of %s", url)
    url.onboarded = True
    url.onboarded_on = timezone.now()
    url.onboarding_stage = "onboarded"
    url.onboarding_stage_set_on = datetime.now(pytz.utc)
    url.save(update_fields=["onboarded_on", "onboarded", "onboarding_stage", "onboarding_stage_set_on"])
    return True


@app.task(queue="storage")
def update_stage(urls: List[Url], stage=""):

    for url in urls:
        log.info("Updating onboarding_stage of %s from %s to %s", url, url.onboarding_stage, stage)
        url.onboarding_stage = stage
        url.onboarding_stage_set_on = datetime.now(pytz.utc)
        url.save(update_fields=["onboarding_stage", "onboarding_stage_set_on"])

    return True
