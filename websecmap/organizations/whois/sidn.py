from typing import Optional

import requests
from time import sleep
import json

from websecmap.app import log
from websecmap.celery import app
from websecmap.organizations.models import Url, UrlWhois


@app.task(queue="storage")
def update_whois_data(**kwargs):
    # url = https://api.sidn.nl/rest/whois?domain=platformhoutrook.nl

    sleep_time = kwargs.get("rate_limit_in_seconds", 30)

    for url in Url.objects.all().filter(computed_subdomain=""):
        # don't be greedy, just take a few days to find everything. The point is not to be up to date to the minute.
        sleep(sleep_time)
        whois_data = get_whois_data(url.url)

        log.debug(whois_data)

        parsed_whois_data = parse_whois_data(url, whois_data)
        if parsed_whois_data:
            save_whois_data(url, parsed_whois_data)


def get_whois_data(url: str) -> str:
    response = requests.get(f"https://api.sidn.nl/rest/whois?domain={url}")
    return response.text


def parse_whois_data(url: Url, whois_data: str) -> Optional[UrlWhois]:
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

    return UrlWhois(
        url=url,
        is_the_latest=True,
        registrant=data.get("details", {}).get("registrant", ""),
        creation_date=data.get("details", {}).get("creationDate", ""),
        updated_date=data.get("details", {}).get("updatedDate", ""),
        admin_contact=data.get("details", {}).get("adminContact", ""),
        reseller=data.get("details", {}).get("reseller", ""),
        abuse=data.get("details", {}).get("abuse", ""),
        whois_record_data=data,
        whois_record_type="json",
    )


def save_whois_data(url: Url, new_whois_data: UrlWhois) -> None:
    latest_whois_data = UrlWhois.objects.filter(url=url, is_the_latest=True).first()

    if not latest_whois_data:
        log.debug("New whois information found for %s!", url)
        new_whois_data.save()
        return

    if str(latest_whois_data.updated_date) == str(new_whois_data.updated_date):
        log.debug("No new whois information found.")
        return

    log.debug("Updating whois data for %s, info has new date: %s", url, new_whois_data.updated_date)

    latest_whois_data.is_the_latest = False
    latest_whois_data.save()
    new_whois_data.save()
