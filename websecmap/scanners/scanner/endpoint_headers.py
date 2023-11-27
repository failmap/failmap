from typing import Any, Dict

import requests

from celery import group

from websecmap.celery import app
from websecmap.scanners.models import Endpoint, HttpEndpointHeaders

from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES
from websecmap.scanners.time_storage import abstract_time_storage


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
        response = requests.head(f"{uri}{path}", stream=True, verify=False, timeout=30, allow_redirects=True)
    except requests.exceptions.RequestException:
        # many things can happen: timeouts, protocol errors, connection errors, you name it.
        return {"error": True}

    # can be serialized
    return {
        "headers": dict(response.headers),
        # For technical reasons, we need to save this as a dict so the has_keys query will work. That
        # has_key does not work on lists.
        "header_names": {key.lower(): "" for key in dict(response.headers)},
    }


@app.task(queue="storage", ignore_result=True)
def store(response: Dict[str, Any], endpoint_id: int):
    endpoint = Endpoint.objects.filter(id=endpoint_id).first()
    if not endpoint or not response or "error" in response:
        return

    # allow only stable headers that don't have randomizers and such. Note the lower case field names.
    stable_header_names = ["content-type"]
    filtered_headers = {key: value for key, value in response["headers"].items() if key.lower() in stable_header_names}

    response["headers"] = filtered_headers
    response["endpoint"] = endpoint

    abstract_time_storage(
        HttpEndpointHeaders,
        fields_to_retrieve_latest={"endpoint": endpoint},
        fields_that_signify_change=["headers", "header_names"],
        data_for_new_record=response,
    )
