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

import logging
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO

import pytz
import requests
from celery import group
from constance import config
from django.conf import settings
from django.core.files import File
from django.db.models import Q
from PIL import Image

from websecmap.celery import app
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint, Screenshot
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import (endpoint_filters, q_configurations_to_scan,
                                                 unique_and_random)
from websecmap.scanners.timeout import timeout

log = logging.getLogger(__package__)


def filter_scan(organizations_filter: dict = dict(),
                urls_filter: dict = dict(),
                endpoints_filter: dict = dict(),
                **kwargs):
    # basically updates screenshots. It will ignore whatever parameter you throw at it as creating screenshots every day
    # is a bit nonsense. It will update every month.
    one_month_ago = datetime.now(pytz.utc) - timedelta(days=31)

    # chromium also understands FTP servers and renders those
    endpoints = Endpoint.objects.all().filter(
        q_configurations_to_scan(level="endpoint"),
        is_dead=False,
        url__not_resolvable=False,
        url__is_dead=False,
        protocol__in=['http', 'https', 'ftp'],
        port__in=[80, 443, 8443, 8080, 8888, 21]
    )
    # Without screenshot OR with a screenshot over a month ago
    endpoints = endpoints.filter((Q(screenshot__isnull=True) | Q(screenshot__created_on__lt=one_month_ago)))

    # It's possible to overwrite the above query also, you can add whatever you want to the normal query.
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)
    return unique_and_random([endpoint.url for endpoint in endpoints])


@app.task(queue='storage')
def plan_scan(organizations_filter: dict = dict(),
              urls_filter: dict = dict(),
              endpoints_filter: dict = dict(),
              **kwargs
              ):
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="screenshot", urls=urls)


@app.task(queue='storage')
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner="ftp", amount=kwargs.get('amount', 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    endpoints = retrieve_endpoints_from_urls(
        urls,
        protocols=['ftp', 'http', 'https'],
        ports=[80, 443, 8443, 8080, 8888, 21]
    )

    endpoints = unique_and_random(endpoints)

    # prevent constance from looking up the value constantly:
    v4_service = config.SCREENSHOT_API_URL_V4
    v6_service = config.SCREENSHOT_API_URL_V6

    log.info(f"Trying to make {len(endpoints)} screenshots.")
    log.info(f"Screenshots will be stored at: {settings.MEDIA_ROOT}screenshots/")
    log.info(f"IPv4 screenshot service: {v4_service}, IPv6 screenshot service: {v6_service}")
    tasks = [make_screenshot.si(v4_service, endpoint.uri_url())
             | save_screenshot.s(endpoint) for endpoint in endpoints if endpoint.ip_version == 4]
    tasks += [make_screenshot.si(v6_service, endpoint.uri_url())
              | save_screenshot.s(endpoint) for endpoint in endpoints if endpoint.ip_version == 6]

    return group(tasks)


# We expect the screenshot tool to hang at non responsive urls.
@app.task(queue='internet', rate_limit="60/m")
def make_screenshot(service, endpoint):
    try:
        return make_screenshot_with_u2p(service, endpoint)
    except (ConnectionError, TimeoutError) as e:
        return e
    except Exception as e:
        return e


@timeout(20, 'Took too long to make screenshot.')
def make_screenshot_with_u2p(screenshot_service, url):
    get_parameters = {
        'output': 'screenshot',
        'url': url,
        'viewport.width': 1280,
        'viewport.height': 720,

        # also give a result when a 404, https error or whatever is given
        'ignoreHttpsErrors': True,

        # gives only the first 'screen' of the page, not the entire page.
        'screenshot.fullPage': False,
    }
    api_call = f"{screenshot_service}/api/render?{urllib.parse.urlencode(get_parameters)}"
    # https://2.python-requests.org/en/latest/user/quickstart/#binary-response-content
    return requests.get(api_call)


@app.task(queue='storage')
def save_screenshot(response, endpoint):

    # it might receive an exception, or "False" when there is no image data due to errors.
    if isinstance(response, TimeoutError):
        log.debug(f"Received exception at save screenshot, not saving. Probably took too long to paint page due to"
                  f"a too complex page or a terribly slow server. This is business as usual. Details: {response}")
        return False

    if isinstance(response, Exception):
        log.exception(f"Received unexpected exception at save screenshot, not saving. "
                      f"Is the screenshot service available at this address? Details: {response}")
        return False

    # with an invalid / non-resolvable address, a 500 error is given by the image service.
    if response.status_code == 500:
        log.debug(f"Received 500 at the API from {endpoint.uri_url()}, url probably does not resolve. "
                  f"This is business as usual. Not saving.")
        return False

    try:
        i = Image.open(BytesIO(response.content))
        size = 320, 240
        i.thumbnail(size, Image.ANTIALIAS)
        filename = f"{settings.MEDIA_ROOT}screenshots/{endpoint.id}_latest.png"
        i.save(filename, "PNG")
        log.debug(f'Image saved as: {filename}.')

        scr = Screenshot()
        scr.created_on = datetime.now(pytz.utc).date()
        scr.endpoint = endpoint
        scr.image = File(open(filename, 'rb'))
        scr.filename = filename
        scr.save()
        log.debug(f"Saved in databased as id:{scr.pk} filename:{scr.filename}.")
    except Exception as e:
        log.exception(e)
