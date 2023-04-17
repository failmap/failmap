from multiprocessing.pool import ThreadPool
from typing import Optional, Union, Any, Dict, List

import requests
from time import sleep
import json

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.models import Url, UrlWhois
from websecmap.scanners.models import ScanProxy


MAX_WHOIS_PER_IP = 500
DEFAULT_SLEEP_PER_REQUEST = 10
MAX_DEPTH = 6
SLEEP_MULTIPLIER = 1.7


@app.task(queue="storage")
def update_whois_data(**kwargs):
    # url = https://api.sidn.nl/rest/whois?domain=platformhoutrook.nl

    sleep_time = kwargs.get("rate_limit_in_seconds", DEFAULT_SLEEP_PER_REQUEST)

    # they have a rate limit of MAX_WHOIS_PER_IP requests per day, per ip
    urls_to_process = list(
        Url.objects.all()
        .filter(computed_subdomain="", is_dead=False, not_resolvable=False)
        .only("id", "url")
        .order_by("?")
        .values("id", "url")
    )

    amount_of_proxies = ScanProxy.objects.all().count()
    if amount_of_proxies == 0:
        # use the classic direct way to get whois data, MAX_WHOIS_PER_IP per day
        log.warning(f"Can only fetch {MAX_WHOIS_PER_IP} whois records per day without proxies.")
        get_stuff(urls_to_process, sleep_time)
        return

    log.debug(f"Found {amount_of_proxies} proxies, spreading whois queries over proxies.")

    # with proxies spread the load over various proxies each up until the daily limit
    # this limit is purely artifical to prevent commercial vendors from selling the data etc / their abuse policy
    # websecmap uses it for legit purposes, but we can't wait a weeks to get all domain information.
    # so spread it over a bunch of tasks and get all the data on the same day.
    # a realistic amount of top level domains is up to 20.000
    amount_of_batches = (len(urls_to_process) // MAX_WHOIS_PER_IP) + 1
    proxies = ScanProxy.objects.all().order_by("?")

    pool = ThreadPool(amount_of_batches)
    for batch in batch_list(urls_to_process, MAX_WHOIS_PER_IP):
        proxy = next(proxies.iterator())
        pool.apply_async(get_stuff, [batch, sleep_time, proxy.protocol, proxy.address])
        sleep(1)

    pool.close()
    pool.join()


def batch_list(my_list: List[Dict[str, Any]], batch_size: int = MAX_WHOIS_PER_IP):
    for i in range(0, len(my_list), batch_size):
        yield my_list[i : i + batch_size]


def get_stuff(
    urls_to_process: List[Dict[str, Any]],
    sleep_time: int = DEFAULT_SLEEP_PER_REQUEST,
    proxy_protocol: str = None,
    proxy_address: str = None,
) -> None:

    for url in urls_to_process:
        whois_data = unlimited_try_to_fetch_data(url["url"], sleep_time, 0, proxy_protocol, proxy_address)
        if whois_data:
            save_whois_data(url["id"], whois_data)


def unlimited_try_to_fetch_data(
    url: str,
    sleep_time: int = DEFAULT_SLEEP_PER_REQUEST,
    depth: int = 0,
    proxy_protocol: str = None,
    proxy_address: str = None,
) -> Optional[UrlWhois]:

    sleep(sleep_time)

    if depth > MAX_DEPTH:
        log.error("SIDN Whois API could not be reached anymore.")
        return None

    whois_data = get_whois_data(url, proxy_protocol, proxy_address)
    parsed_whois_data = parse_whois_data(whois_data)

    if not isinstance(parsed_whois_data, UrlWhois):
        if parsed_whois_data == 429:
            depth += 1
            sleep_time *= SLEEP_MULTIPLIER
            parsed_whois_data = unlimited_try_to_fetch_data(url, sleep_time, depth, proxy_protocol, proxy_address)

        if parsed_whois_data == 403:
            return None

    return parsed_whois_data


def get_whois_data(url: str, proxy_protocol: str = None, proxy_address: str = None) -> str:
    # since there is a limit of MAX_WHOIS_PER_IP requests per day, per ip, just use a series of proxies to get
    # all the data needed.
    if proxy_protocol and proxy_address:
        response = requests.get(
            f"https://api.sidn.nl/rest/whois?domain={url}", proxies={proxy_protocol: proxy_address}, timeout=30
        )
    else:
        response = requests.get(f"https://api.sidn.nl/rest/whois?domain={url}", timeout=30)
    return response.text


def parse_whois_data(whois_data: str) -> Union[Optional[UrlWhois], int]:
    """
    {
      "type": "WHO_IS",
      "status": {
        "code": 200,
        "message": "OK"
      },
      "errors": [],
      "warnings": [
        {
          "type": "CLEANUP_DETECT_URL"
        }
      ],
      "changed": false,
      "details": {
        "domain": "sidn.nl",
        "state": {
          "type": "ACTIVE"
        },
        "registrar": "Stichting Internet Domeinregistratie Nederland\nMeander 501\n6825MD Arnhem\nNetherlands",
        "abuse": "+31.263525555\nabuse@sidn.nl",
        "dnsSec": true,
        "nameServers": [
          {
            "hostname": "ns4.sidn.nl",
            "ip-address": "212.114.120.108"
          },
          {
            "hostname": "ns4.sidn.nl",
            "ip-address": "2001:7b8:62b:1:0:d4ff:fe72:786c"
          },
          {
            "hostname": "ns5.sidn.nl",
            "ip-address": "2604:1380:4601:6300::1"
          },
          {
            "hostname": "ns5.sidn.nl",
            "ip-address": "145.40.68.55"
          },
          {
            "hostname": "ns3.sidn.nl",
            "ip-address": "2001:678:34:0:194:0:30:2"
          },
          {
            "hostname": "ns3.sidn.nl",
            "ip-address": "194.0.30.2"
          }
        ],
        "creationDate": "1999-11-18",
        "updatedDate": "2021-10-14",
        "maintainer": "NL Domain Registry",
        "registrant": "Stichting Internet Domeinregistratie Nederland",
        "adminContact": "support@sidn.nl",
        "techContacts": [
          "support@sidn.nl"
        ],
        "optOut": false,
        "domicile": false,
        "copyright": "Copyright notice No part of this publication may be reproduced, published, stored in a retrieval system, or transmitted, in any form or by any means, electronic, mechanical, recording, or otherwise, without prior permission of the Foundation for Internet Domain Registration in the Netherlands (SIDN). These restrictions apply equally to registrars, except in that reproductions and publications are permitted insofar as they are reasonable, necessary and solely in the context of the registration activities referred to in the General Terms and Conditions for .nl Registrars. Any use of this material for advertising, targeting commercial offers or similar activities is explicitly forbidden and liable to result in legal action. Anyone who is aware or suspects that such activities are taking place is asked to inform the Foundation for Internet Domain Registration in the Netherlands. ©The Foundation for Internet Domain Registration in the Netherlands (SIDN) Dutch Copyright Act, protection of authors' rights (Section 10, subsection 1, clause 1)."  # noqa
      },
      "_links": {
        "self": {
          "href": "https://api.sidn.nl/rest/whois?domain=sidn.nl"
        }
      }
    }
    """
    try:
        whois_data = whois_data.replace("\n", "\\n")
        data = json.loads(whois_data)
    except json.decoder.JSONDecodeError as e:
        log.error("Could not parse whois data: %s", e)
        return None

    # {"code":429,"error":"Too many requests","id":"1fG5msV_Q2SZ_rjsgVQsBA"}
    if data.get("code") == 429:
        log.debug("Too many requests!")
        return 429

    # {'code': 403, 'error': 'Daily limit exceeded', 'id': '8qABiz8SQeC6zo4mqg-6tw'}
    if data.get("code") == 403:
        log.debug("Daily limit exceeded!")
        return 403

    return UrlWhois(
        is_the_latest=True,
        registrant=data.get("details", {}).get("registrant", ""),
        creation_date=data.get("details", {}).get("creationDate", None),
        updated_date=data.get("details", {}).get("updatedDate", None),
        admin_contact=data.get("details", {}).get("adminContact", ""),
        reseller=data.get("details", {}).get("reseller", ""),
        abuse=data.get("details", {}).get("abuse", ""),
        whois_record_data=data,
        whois_record_type="json",
    )


def save_whois_data(url_id: int, new_whois_data: UrlWhois) -> None:
    url = Url.objects.all().filter(id=url_id).first()
    if not url:
        log.error("Could not find url with id: %s", url_id)
        return

    latest_whois_data = UrlWhois.objects.filter(url=url, is_the_latest=True).first()
    new_whois_data.url = url

    if not latest_whois_data:
        # save regardless of date info
        log.debug("New whois information found for %s!", url)
        new_whois_data.save()
        return
    if not new_whois_data.updated_date:
        # no date info, so we can't be sure to update... skip for now...
        log.debug("No date info found for %s, skipping update.", url)
        return
    if str(latest_whois_data.updated_date) == str(new_whois_data.updated_date):
        log.debug("No new whois information found.")
        return

    log.debug("Updating whois data for %s, info has new date: %s", url, new_whois_data.updated_date)
    latest_whois_data.is_the_latest = False
    latest_whois_data.save()
    new_whois_data.save()
