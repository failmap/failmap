import json
import logging
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import Any, Dict, List, Optional, Union

import requests

from websecmap.celery import app
from websecmap.organizations.models import Url, UrlWhois
from websecmap.scanners.models import ScanProxy

log = logging.getLogger(__name__)

MAX_WHOIS_PER_IP = 500
DEFAULT_SLEEP_PER_REQUEST = 10
MAX_DEPTH = 6
SLEEP_MULTIPLIER = 1.7


@app.task(queue="database", ignore_result=True)
def update_whois_data(**kwargs):
    # url = https://api.sidn.nl/rest/whois?domain=platformhoutrook.nl

    sleep_time = kwargs.get("rate_limit_in_seconds", DEFAULT_SLEEP_PER_REQUEST)

    # they have a rate limit of MAX_WHOIS_PER_IP requests per day, per ip
    # SIDN Whois only returns answers for .nl. You CAN ask for a .com but will answer with .nl data,
    # which is sneaky. It will just strip the TLD and answer for its own data.
    # clean your db with:
    #
    # UrlGenericScan.objects.all().filter(type="whois_domain_ownership",
    #  url__in=Url.objects.all().filter(computed_subdomain="").exclude(computed_suffix="nl")).delete()
    urls_to_process = list(
        Url.objects.all()
        .filter(computed_subdomain="", computed_suffix="nl", is_dead=False, not_resolvable=False)
        .only("id", "url")
        .order_by("?")
        .values("id", "url")
    )

    amount_of_proxies = ScanProxy.objects.all().count()
    if amount_of_proxies == 0:
        # use the classic direct way to get whois data, MAX_WHOIS_PER_IP per day
        log.warning("Can only fetch %s whois records per day without proxies.", MAX_WHOIS_PER_IP)
        get_stuff(urls_to_process, sleep_time)
        return

    log.debug("Found %s proxies, spreading whois queries over proxies.", amount_of_proxies)

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
        "copyright": "Copyright notice No part of this ..."
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

    # accept non breaking spaces and other weird invisible stuff from registrants
    return UrlWhois(
        is_the_latest=True,
        registrant=clean_registrant(data.get("details", {}).get("registrant", "")),
        creation_date=data.get("details", {}).get("creationDate", None),
        updated_date=data.get("details", {}).get("updatedDate", None),
        admin_contact=data.get("details", {}).get("adminContact", ""),
        reseller=data.get("details", {}).get("reseller", ""),
        abuse=data.get("details", {}).get("abuse", ""),
        whois_record_data=data,
        whois_record_type="json",
    )


def clean_registrant(registrant: str) -> str:
    # https://unicode-explorer.com/articles/space-characters
    # trim registrant and replace all possible weird unicode spaces with normal spaces
    spaces = [
        "\xA0",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u202f",
        "\u205f",
        "\u3000",
        "\u200B",
        "\u200C",
        "\u200D",
        "\u2060",
        "\uffef",
        "\u180e",
        "\u2800",
        "\u3164",
    ]
    for space in spaces:
        if space in registrant:
            registrant = registrant.replace(space, " ")
    return registrant.strip()


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
