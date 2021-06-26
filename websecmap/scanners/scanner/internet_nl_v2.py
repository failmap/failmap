"""
Implementation of Internet.nl API v2.0

Docs: https://api.internet.nl/v2/documentation/

Internet.nl scans for modern web and mail standards. Such as https, SPF, DNS Security, START TLS and more...

All functions return a status code and contents retrieved (if applicable). A special status code 599 is being used
to log network errors. These errors can be retried.
"""

import logging
from typing import List, Any, Dict

import requests
from requests.auth import HTTPBasicAuth

from websecmap.celery import app

log = logging.getLogger(__name__)


class InternetNLApiSettings:
    url: str = ""
    username: str = ""
    password: str = ""
    maximum_domains: int = 5000


def return_safe_response(answer):
    # Only with a status code of 200 and 512 a json message is returned.
    if answer.status_code in [200, 512]:
        return answer.status_code, answer.json()

    # may have any status, which maps to api specifications.
    return answer.status_code, {}


@app.task(queue="storage")
def register(domains: List[str], scan_type: str, tracking_information: str, settings: Dict[str, Any]) -> (str, str):

    data = {"type": scan_type, "name": tracking_information, "domains": domains}

    try:
        response = requests.post(
            f"{settings['url']}/requests",
            json=data,
            auth=HTTPBasicAuth(settings["username"], settings["password"]),
            timeout=(300, 300),
        )
    except requests.RequestException as e:
        # This is returned as a catch all for network errors. A network error can be retried.
        return 599, {"network_error": f"{e.strerror} {repr(e)}"}

    return return_safe_response(response)


@app.task(queue="storage")
def metadata(settings: Dict[str, Any]):
    return generic_internet_nl_api_request("get", f"{settings['url']}/metadata/report", settings)


@app.task(queue="storage")
def status(scan_id: int, settings: Dict[str, Any]):
    return generic_internet_nl_api_request("get", f"{settings['url']}/requests/{scan_id}", settings)


@app.task(queue="storage")
def cancel(scan_id: int, settings: Dict[str, Any]):
    return generic_internet_nl_api_request("patch", f"{settings['url']}/requests/{scan_id}", settings)


@app.task(queue="storage")
def result(scan_id: int, settings: Dict[str, Any]):
    return generic_internet_nl_api_request("get", f"{settings['url']}/requests/{scan_id}/results", settings)


def generic_internet_nl_api_request(operation, url: str, settings: Dict[str, Any]):
    # We're dealing with all kinds of network issues by returning a network issue as a status code.
    # Network issues can be recovered and the next step can be retried. Network issues can take a long time and
    # should not break the process of gathering results.

    try:
        requests_function = getattr(requests, operation)
        response = requests_function(
            url, auth=HTTPBasicAuth(settings["username"], settings["password"]), timeout=(300, 300)
        )
    except requests.RequestException as e:
        return 599, {"network_error": f"{e.strerror} {repr(e)}"}

    return return_safe_response(response)
