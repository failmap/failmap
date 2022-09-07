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
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, Union

import pytz
import requests
from celery import Task, group
from constance import config
from django.conf import settings
from django.db.models import Q
from PIL import Image, UnidentifiedImageError

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, Screenshot
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import endpoint_filters, q_configurations_to_scan, unique_and_random
from websecmap.scanners.timeout import timeout

log = logging.getLogger(__package__)


def filter_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    # basically updates screenshots. It will ignore whatever parameter you throw at it as creating screenshots every day
    # is a bit nonsense. It will update every month.
    one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

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


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="screenshot", urls=urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner="screenshot", amount=kwargs.get("amount", 25))
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
        plannedscan.finish("scan", "screenshot", url_id)

    # prevent constance from looking up the value constantly:
    v4_service = config.SCREENSHOT_API_URL_V4
    v6_service = config.SCREENSHOT_API_URL_V6

    log.debug("Trying to make %s screenshots.", len(endpoints))
    log.debug("Screenshots will be stored at: %sscreenshots/", settings.MEDIA_ROOT)
    log.debug("IPv4 screenshot service: %s, IPv6 screenshot service: %s", v4_service, v6_service)
    tasks = []
    if v4_service:
        tasks += [
            make_screenshot.si(v4_service, endpoint.uri_url()) | save_screenshot.s(endpoint.id)
            for endpoint in endpoints
            if endpoint.ip_version == 4
        ]
    if v6_service:
        tasks += [
            make_screenshot.si(v6_service, endpoint.uri_url()) | save_screenshot.s(endpoint.id)
            for endpoint in endpoints
            if endpoint.ip_version == 6
        ]

    return group(tasks)


# We expect the screenshot tool to hang at non responsive urls.
@app.task(queue="screenshot", expires=EXPIRES_IN_ONE_DAY)
def make_screenshot(service: str, endpoint_url: str):
    try:
        return make_screenshot_with_browserless(service, endpoint_url)
    except (ConnectionError, TimeoutError) as my_exception:
        log.debug("Error while making screenshot on %s", endpoint_url)
        return my_exception
    except Exception as my_exception:  # pylint: disable=broad-except
        return my_exception


@timeout(30, "Took too long to make screenshot.")
def make_screenshot_with_browserless(screenshot_service: str, url: str) -> Dict[str, Union[str, bool, int]]:
    # https://2.python-requests.org/en/latest/user/quickstart/#binary-response-content

    try:
        answer = requests.post(
            screenshot_service,
            json={
                "url": url,
                "options": {
                    "fullPage": False,
                    "type": "png",
                    # "clip": {"height": 720, "width": 1280, "x": 0, "y": 0},
                },
            },
        )

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
    except requests.RequestException as exc:
        return {
            "screenshot": b"",
            "status_code": 0,
            "success": False,
            "error_message": str(exc),
            "url": url,
            "screenshot_service": screenshot_service,
        }


def deserialize_image_to_image(image_data: str) -> Image:
    return Image.open(BytesIO(base64.b64decode(image_data.encode(encoding="utf-8"))))


def determine_subdir(sequence_number: int) -> str:
    if sequence_number <= 999:
        return "000"
    return str(sequence_number)[0:3]


def create_dir_if_not_exists(directory: str):
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
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
        i.thumbnail(size, Image.ANTIALIAS)
        i.save(filename, "PNG")
        log.debug("Image saved as: %s.", filename)

        # administration of the image, which is used to plan scans
        scr = Screenshot()
        scr.created_on = datetime.now(pytz.utc).date()
        scr.endpoint = Endpoint.objects.all().get(id=endpoint_id)
        scr.filename = filename
        scr.save()
        return True
    except UnidentifiedImageError:
        log.debug("Got Unidentified Image, response: ")
        log.debug(response)
    except Exception as my_exception:  # pylint: disable=broad-except
        log.exception(my_exception)

    return False
