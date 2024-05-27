from typing import Any, Dict

import niquests

from celery import group

from websecmap.celery import app
from websecmap.scanners.models import Endpoint, HttpEndpointHeaders

from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES
from websecmap.scanners.time_storage import abstract_time_storage
import logging

log = logging.getLogger(__name__)


@app.task(queue="kickoff")
def get_content():
    endpoints = Endpoint.objects.all().filter(
        protocol__in=["http", "https"], is_dead=False, url__is_dead=False, url__not_resolvable=False
    )

    tasks = [
        # queue dynamically set depending if this is v4 or v6 internet
        scan.s(endpoint.uri_url(), "/").set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
        | store.s(endpoint.id)
        for endpoint in endpoints
    ]

    group(tasks).apply_async()


@app.task()
def scan(uri, path):
    try:
        # TODO: used for debugging hanging issues, can be removed when they are solved
        log.info("starting request to %s", uri)

        # perform HEAD request, ignore HTTPS errors, use happy eyeballs to pick the first of ipv4/6 to respond
        # follow redirect, do not wait until  all content is downloaded and timeout in 30 seconds
        # 'requests' doesn't do happy eyeballs, 'niquests' does and should be a drop in replacement
        # https://github.com/jawah/niquests/releases/tag/v3.5.5
        with niquests.Session(happy_eyeballs=True) as s:
            response = s.head(f"{uri}{path}", stream=True, verify=False, timeout=30, allow_redirects=True)

        log.info("finished request to %s", uri)
    except niquests.exceptions.RequestException:
        log.info("failed request to %s", uri)

        # many things can happen: timeouts, protocol errors, connection errors, you name it.
        return {"uri": uri, "path": path, "error": True}

    # can be serialized
    return {
        "uri": uri,
        "path": path,
        "headers": dict(response.headers),
        # For technical reasons, we need to save this as a dict so the has_keys query will work. That
        # has_key does not work on lists. Servers give headers in changing orders. Sort them to create stable data.
        "header_names": {key.lower(): "" for key in list(sorted(dict(response.headers)))},
    }


@app.task(queue="storage", ignore_result=True)
def store(response: Dict[str, Any], endpoint_id: int):
    endpoint = Endpoint.objects.filter(id=endpoint_id).first()
    if not endpoint or not response or "error" in response:
        return

    # allow only stable headers that don't have randomizers and such. Note the lower case field names.
    # make all header names lowercase. This also reduces multiple of the same headers into one.
    # also make the content itself lowercase for easier searching.
    # this is auto-sorted
    stable_header_names = ["content-type"]
    filtered_headers = {
        key.lower(): value.lower() for key, value in response["headers"].items() if key.lower() in stable_header_names
    }

    response["headers"] = filtered_headers
    response["endpoint"] = endpoint

    abstract_time_storage(
        HttpEndpointHeaders,
        fields_to_retrieve_latest={"endpoint": endpoint},
        fields_that_signify_change=["headers", "header_names"],
        data_for_new_record=response,
    )
