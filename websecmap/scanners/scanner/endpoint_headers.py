from typing import Any, Dict
from websecmap.celery.worker import WORKER_ROLE
import niquests


from websecmap.celery import app
from websecmap.scanners.models import Endpoint, HttpEndpointHeaders

from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES
from websecmap.scanners.time_storage import abstract_time_storage
import logging

log = logging.getLogger(__name__)

DISABLE_IPV6 = WORKER_ROLE == "v4_internet"
DISABLE_IPV4 = WORKER_ROLE == "v6_internet"

# maximum amount of time allowed to connect and get the headers
TIMEOUT = 30


@app.task(queue="kickoff")
def get_content():
    # using iterators improves performance, especially on postgresql:
    # https://docs.djangoproject.com/en/5.0/ref/models/querysets/#with-server-side-cursors
    endpoints = (
        Endpoint.objects.all()
        .filter(protocol__in=["http", "https"], is_dead=False, url__is_dead=False, url__not_resolvable=False)
        .iterator()
    )

    for endpoint in endpoints:
        # queue dynamically set depending if this is v4 or v6 internet
        (
            scan.s(endpoint.uri_url(), "/").set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
            | store.s(endpoint.id)
        ).apply_async()


@app.task(time_limit=TIMEOUT * 2)
def scan(uri, path):
    try:
        # perform HEAD request, ignore HTTPS errors, disable the ip protocol that this worker does not use
        # follow redirect, do not wait until  all content is downloaded and timeout in 30 seconds
        # 'requests' doesn't do happy eyeballs, 'niquests' does and should be a drop in replacement
        # https://github.com/jawah/niquests/releases/tag/v3.5.5
        with niquests.Session(disable_ipv4=DISABLE_IPV4, disable_ipv6=DISABLE_IPV6) as session:
            response = session.head(f"{uri}{path}", stream=True, verify=False, timeout=TIMEOUT, allow_redirects=True)
    except niquests.exceptions.RequestException as e:
        log.warning("failed to get headers on: %s, due to error: %s", uri, str(e))

        # many things can happen: timeouts, protocol errors, connection errors, you name it.
        return {"error": True}

    # can be serialized
    return {
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
