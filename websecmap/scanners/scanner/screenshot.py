"""
Uses a docker container / service to retrieve screenshots.

Using: https://github.com/alvarcarto/url-to-pdf-api
In docker container: https://github.com/microbox/node-url-to-pdf-api

API examples:
https://github.com/alvarcarto/url-to-pdf-api

Test url:
https://url-to-pdf-api.herokuapp.com

Uses configuration setting:
SCREENSHOT_API_URL_V4
SCREENSHOT_API_URL_V6
Which defaults to:
http://screenshot_v4:1337
http://screenshot_v6:1337
"""
import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, Union
import json

import requests
from celery import Task, group
from constance import config
from django.conf import settings
from django.db.models import Q
from PIL import Image, UnidentifiedImageError

from websecmap.celery import app
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, Screenshot
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import endpoint_filters, q_configurations_to_scan, unique_and_random
from websecmap.scanners.timeout import timeout

log = logging.getLogger(__package__)

SCANNER_NAME = "screenshot"
SCANNER_ACTION = "scan"

PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def filter_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    # basically updates screenshots. It will ignore whatever parameter you throw at it as creating screenshots every day
    # is a bit nonsense. It will update every month.
    one_month_ago = datetime.now(timezone.utc) - timedelta(days=31)

    # chromium also understands FTP servers and renders those
    endpoints = Endpoint.objects.all().filter(
        q_configurations_to_scan(level="endpoint"),
        is_dead=False,
        url__not_resolvable=False,
        url__is_dead=False,
        protocol__in=["http", "https", "dns_a_aaaa"],
        port__in=[80, 443, 8443, 8080, 8888, 21, 0],
    )
    # Without screenshot OR with a screenshot over a month ago
    endpoints = endpoints.filter((Q(screenshot__isnull=True) | Q(screenshot__created_on__lt=one_month_ago)))

    # It's possible to overwrite the above query also, you can add whatever you want to the normal query.
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)
    return unique_and_random([endpoint.url for endpoint in endpoints])


@app.task(queue="kickoff", ignore_result=True)
def plan_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity=SCANNER_ACTION, scanner=SCANNER_NAME, urls=urls)


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity=SCANNER_ACTION, scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls):
    endpoints, urls_without_endpoints = retrieve_endpoints_from_urls(
        urls, protocols=["http", "https", "dns_a_aaaa"], ports=[80, 443, 8443, 8080, 8888, 21, 0]
    )

    endpoints = unique_and_random(endpoints)

    # remove urls that don't have the relevant endpoints anymore
    for url_id in urls_without_endpoints:
        plannedscan.finish(SCANNER_ACTION, SCANNER_NAME, url_id)

    # prevent constance from looking up the value constantly:
    v4_service = config.SCREENSHOT_API_URL_V4
    v6_service = config.SCREENSHOT_API_URL_V6

    log.debug("Trying to make %s screenshots.", len(endpoints))
    log.debug("Screenshots will be stored at: %sscreenshots/", settings.MEDIA_ROOT)
    log.debug("IPv4 screenshot service: %s, IPv6 screenshot service: %s", v4_service, v6_service)
    tasks = []
    if v4_service:
        tasks += [
            make_screenshot.si(v4_service, endpoint.uri_url())
            | save_screenshot.s(endpoint.id)
            | plannedscan.finish.si(SCANNER_ACTION, SCANNER_NAME, endpoint.url.pk)
            for endpoint in endpoints
            if endpoint.ip_version in [4, 0]
        ]
    if v6_service:
        tasks += [
            make_screenshot.si(v6_service, endpoint.uri_url()) | save_screenshot.s(endpoint.id)
            # might finish it twice, but that's better than not finishing it at al.
            # and we want to finish asap, not after all scans are made...
            | plannedscan.finish.si(SCANNER_ACTION, SCANNER_NAME, endpoint.url.pk)
            for endpoint in endpoints
            # For v6 you may also scan dns_a_aaaa to see if there is a site at the v6 address.
            if endpoint.ip_version in [6]
        ]

    return group(tasks)


# We expect the screenshot tool to hang at non responsive urls.
@app.task(queue="screenshot")
def make_screenshot(service: str, endpoint_url: str) -> Dict[str, Any]:
    try:
        return make_screenshot_with_browserless(service, endpoint_url)
    except TimeoutError:
        # took too long to make the screenshot, this is business as usual
        return {"success": False}


@timeout(30, "Took too long to make screenshot.")
def make_screenshot_with_browserless(screenshot_service: str, url: str) -> Dict[str, Union[str, bool, int]]:
    # https://2.python-requests.org/en/latest/user/quickstart/#binary-response-content

    message = {
        "url": url,
        "options": {
            "fullPage": False,
            "type": "png",
            # "clip": {"height": 720, "width": 1280, "x": 0, "y": 0},
        },
    }

    log.debug("Doing the equivalent of: curl --fail --data '%s' %s", json.dumps(message), screenshot_service)

    try:
        answer = requests.post(screenshot_service, json=message, timeout=30)
        answer.raise_for_status()

        # make a serializable dict as an answer
        return {
            # binary data
            "screenshot": base64.b64encode(answer.content).decode(encoding="utf-8"),
            "status_code": answer.status_code,
            "success": True,
            "error_message": "",
            "url": url,
            "screenshot_service": screenshot_service,
        }
    except requests.RequestException as e:
        # cannot find service, etc, connection errors, timeouts etc...
        # while business as usual, log it for a while to see what happens
        if hasattr(e, "response"):
            error_message = e.response.content.decode("utf8")[:100]
            status_code = e.response.status_code
        else:
            error_message = str(e)
            status_code = 0
        log.exception("HTTP error during screenshot capture: {error_message}")
        return {
            "screenshot": "",
            "status_code": status_code,
            "success": False,
            "error_message": error_message,
            "url": url,
            "screenshot_service": screenshot_service,
        }
    except Exception as e:  # pylint: disable=broad-except
        # something weird that is not a standard network error.
        log.exception("Unexpected error during screenshot capture")
        return {
            "screenshot": "",
            "status_code": 0,
            "success": False,
            "error_message": str(e),
            "url": url,
            "screenshot_service": screenshot_service,
        }


def deserialize_image_to_image(image_data: str) -> Image:
    return Image.open(BytesIO(base64.b64decode(image_data.encode(encoding="utf-8"))))


def determine_subdir(sequence_number: int) -> str:
    return "000" if sequence_number <= 999 else str(sequence_number)[:3]


def create_dir_if_not_exists(directory: str):
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)


@app.task(queue="database")
def save_screenshot(response: Dict[str, Union[str, bool, int]], endpoint_id: int):
    if not response["success"]:
        log.debug("Could not get screenshot on endpoint %s, returned %s ", endpoint_id, response)
        return False

    try:
        # making sure all storage stuff is prepared
        os.makedirs(f"{settings.MEDIA_ROOT}screenshots/", exist_ok=True)  # screenshot dir might not yet exist
        out_dir: str = f"{settings.MEDIA_ROOT}screenshots/{determine_subdir(endpoint_id)}/"
        filename = f"{out_dir}{endpoint_id}_latest.png"
        create_dir_if_not_exists(out_dir)

        # actual saving of the image to disk
        i = deserialize_image_to_image(response["screenshot"])
        size = 640, 360  # widescreen
        i.thumbnail(size, Image.Resampling.LANCZOS)
        i.save(filename, "PNG")
        log.debug("Image saved as: %s.", filename)

        # administration of the image, which is used to plan scans
        scr = Screenshot()
        scr.created_on = datetime.now(timezone.utc).date()
        scr.endpoint = Endpoint.objects.all().get(id=endpoint_id)
        scr.filename = filename
        scr.save()
        return True
    except UnidentifiedImageError:
        log.debug("Got Unidentified Image, response: ")
        log.debug(response)
    except Exception:  # pylint: disable=broad-except
        log.exception("Unexpected error during screenshot saving")

    return False
