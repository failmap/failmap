from datetime import datetime, timezone
from typing import Any, Dict
import time
import requests

from celery import group
from django.db import OperationalError

from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.models import HttpEndpointContent, Endpoint
import hashlib
from bs4 import BeautifulSoup

from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES
from difflib import SequenceMatcher


@app.task(queue="kickoff")
def get_content():
    endpoints = Endpoint.objects.all().filter(
        protocol__in=["http", "https"], is_dead=False, url__is_dead=False, url__not_resolvable=False
    )

    tasks = [
        # queue dynamically set depending if this is v4 or v6 internet
        get_http_content.s(endpoint.uri_url(), "/").set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
        | store_http_content.s(endpoint.id)
        for endpoint in endpoints
    ]

    group(tasks).apply_async()


@app.task()
def get_http_content(uri, path):
    # queue dynamically set depending if this is v4 or v6 internet
    # this gets data the 'dumb classic way', which might just barely work for front pages, it will certainly
    # not work for crawling ot anything else. Use a Playwright crawler for going further than the base response.
    # be aware that a response can be 10 gigabytes

    try:
        response = requests.get(f"{uri}{path}", stream=True, verify=False, timeout=30, allow_redirects=True)
    except requests.exceptions.RequestException:
        # many things can happen: timeouts, protocol errors, connection errors, you name it.
        return {"error": True}

    data = b""
    for i, block in enumerate(response.iter_content(chunk_size=1024), start=1):
        data += block
        # limit response size to 1 megabyte. 1024 * 1024 bytes
        if i > 1024:
            break
    response.close()

    try:
        data = data.decode("utf-8")
    except UnicodeDecodeError:
        # todo: make it cleaner
        data = "UnicodeDecodeError"
    soup = BeautifulSoup(data, "html.parser")

    # can be serialized
    return {
        "path": path,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "")[:40],
        # soup.get_text() would perhaps be nicer, but might miss non-html content
        # data might be complete garbage with weird continuation characters, incorrect unicode etc...
        "content": str(data),
        "content_hash": hashlib.sha256(str(data).encode()).hexdigest(),
        "title": soup.title.string[:200] if soup and soup.title and soup.title.string else "",
        "length_in_bytes": response.headers.get("content-length", None),
        # the conversio to dict might lose some headers in edge cases
        "headers": dict(response.headers),
    }


@app.task(queue="storage", ignore_result=True)
def store_http_content(response: Dict[str, Any], endpoint_id: int):
    endpoint = Endpoint.objects.filter(id=endpoint_id).first()
    if not endpoint:
        return

    # some other exception happened:
    if not response:
        return

    # silent suppression for now..., Any request exception for example, which will happen all the time.
    if "error" in response:
        return

    if previous := HttpEndpointContent.objects.filter(endpoint=endpoint, is_the_latest=True).first():
        # same stuff, different day, we might miss the headers here...
        # for this the headers need to be stabilized otherwise there are many useless changes.
        # perhaps separate headers.
        if content_is_identical(response["content"], previous.content):
            previous.last_scan_moment = datetime.now(timezone.utc)
            previous.save()
            return

        # new stuff!
        previous.is_the_latest = False
        previous.save()

    try:
        HttpEndpointContent.objects.create(
            endpoint=endpoint,
            is_the_latest=True,
            last_scan_moment=datetime.now(timezone.utc),
            at_when=datetime.now(timezone.utc),
            **response,
        )
    except OperationalError:
        # (1366, "Incorrect string value: '\\xF0\\x9F\\x99\\x82? ...' for column 'content' at row 1")
        return


def content_is_identical(new_content: str, old_content: str, percentage_when_the_same: int = 90):
    # amount_when_the_same is a float representing a percentage. So 0.95 = 95%.
    # TODO: this process is pretty CPU intensive and leads to seconds or minutes of processing time
    # sometimes.
    start = int(time.time())
    ratio = SequenceMatcher(None, new_content, old_content).ratio()
    end = int(time.time())
    log.info(
        (
            f"New content size: {len(new_content)}, old content size: "
            f"{len(old_content)}, took: {end-start} seconds, ratio: {ratio}."
        )
    )
    log.debug("%s similarity.", round(ratio * 100, 2))
    return ratio > percentage_when_the_same / 100


def compare_and_clean_previous_site_copies():
    # walks over previous endpoint content and deletes content that is too similar.
    # of course some pages have changes in timestamps and news feeds and such, but that is usually just a
    # little bit of content.

    # - is "descending order"! Don't get anything except the id, get the content etc later when needed
    # otherwise you're drawing gigabytes of memory
    scans = HttpEndpointContent.objects.all().only("id").order_by("-at_when")
    # check each scan against the previous scan, if the previous is the same, then delete the previous.
    # take into account that the previous scan might have been deleted.
    for scan in scans:
        log.debug("Checking scan %s against previous scans.", scan.id)

        # possible that this scan was deleted
        # use this to get the actual content, so you don't have to get everything in the query above in one take
        scan_still_exists = HttpEndpointContent.objects.filter(id=scan.id).first()
        if not scan_still_exists:
            log.debug("scan %s was deleted.", scan.id)
            continue

        previous_scan = (
            HttpEndpointContent.objects.filter(
                endpoint=scan_still_exists.endpoint, at_when__lt=scan_still_exists.at_when
            )
            .order_by("-at_when")
            .first()
        )

        if not previous_scan:
            log.debug("No previous scans on scan %s.", scan.id)
            continue

        log.debug("Comparing scan %s with previous scan %s.", scan_still_exists.id, previous_scan.id)
        if content_is_identical(scan_still_exists.content, previous_scan.content):
            clean_endpoint_content_scan(staying=scan_still_exists, delete=previous_scan)


def clean_endpoint_content_scan(staying: HttpEndpointContent, delete: HttpEndpointContent):
    staying.at_when = delete.at_when
    staying.save()
    delete.delete()
