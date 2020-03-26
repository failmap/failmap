"""
Implementation of Internet.nl API v2.0

Docs: https://api.internet.nl/v2/documentation/

Internet.nl scans for modern web and mail standards. Such as https, SPF, DNS Security, START TLS and more...

All functions return a status code and contents retrieved (if applicable). A special status code 599 is being used
to log network errors. These errors can be retried.
"""

import logging
from typing import List

import requests
from requests.auth import HTTPBasicAuth

from websecmap.celery import app

log = logging.getLogger(__name__)


class InternetNLApiSettings:
    url: str = ""
    username: str = ""
    password: str = ""
    maximum_domains: int = 5000


def return_save_response(answer):
    # Only with a status code of 200 and 512 a json message is returned.
    if answer.status_code in [200, 512]:
        return answer.status_code, answer.json()

    # may have any status, which maps to api specifications.
    return answer.status_code, {}


@app.task(queue="storage")
def register(domains: List[str], scan_type: str, tracking_information: str,
             settings: InternetNLApiSettings) -> (str, str):

    if len(domains) > settings.maximum_domains:
        raise ValueError("Amount of domains given is higher than the API can handle.")

    data = {
        "type": scan_type,
        "tracking_information": tracking_information,
        "domains": domains
    }

    try:
        response = requests.post(
            f'{settings.url}/scans',
            json=data,
            auth=HTTPBasicAuth(settings.username, settings.password), timeout=(300, 300)
        )
    except requests.RequestException as e:
        # This is returned as a catch all for network errors. A network error can be retried.
        return 599, {"network_error": e.strerror}

    return return_save_response(response)


@app.task(queue="storage")
def metadata(settings: InternetNLApiSettings):

    try:
        response = requests.get(
            f'{settings.url}/scans/metadata',
            auth=HTTPBasicAuth(settings.username, settings.password)
        )
    except requests.RequestException as e:
        return 599, {"network_error": e.strerror}

    return return_save_response(response)


@app.task(queue="storage")
def status(scan_id: int, settings: InternetNLApiSettings):

    try:
        response = requests.get(
            f'{settings.url}/scans/status/{scan_id}',
            auth=HTTPBasicAuth(settings.username, settings.password)
        )
    except requests.RequestException as e:
        return 599, {"network_error": e.strerror}

    return return_save_response(response)


@app.task(queue="storage")
def result(scan_id: int, settings: InternetNLApiSettings):

    try:
        response = requests.get(
            f'{settings.url}/scans/result/{scan_id}',
            auth=HTTPBasicAuth(settings.username, settings.password)
        )
    except requests.RequestException as e:
        return 599, {"network_error": e.strerror}

    return return_save_response(response)
