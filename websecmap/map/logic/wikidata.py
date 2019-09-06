import logging

from urllib3.exceptions import HTTPError
from wikidata.client import Client

log = logging.getLogger(__package__)


OFFICIAL_WEBSITE: str = "P856"
ISO3316_2_COUNTRY_CODE: str = "P297"
ISO3316_2_COUNTY_SUBDIVISION_CODE: str = "P300"


def get_property_from_code(wikidata_code: str, property_code: str):
    """
    Note: this is very inefficient at getting multiple properties.

    :param wikidata_code: Q9928
    :param property_code: P856
    :return:
    """

    if not wikidata_code or not property_code:
        return ""

    # log.debug(f"Wikidata code: {wikidata_code}, property_code: {property_code}")

    try:
        client = Client()

        # reqests without a wikidata code result in raise HTTPError(req.full_url, code, msg, hdrs, fp)
        entity = client.get(wikidata_code, load=True)
        return_value = str(entity.get(client.get(property_code), None))

        if not return_value or return_value == "None":
            log.debug(f"No {property_code} for wikidata code: {wikidata_code}")
            return ""

        return return_value

    except HTTPError:
        # No entity with ID Q15111448 was found... etc.
        # perfectly possible. In that case, no website, and thus continue.
        # As this is a network call, million errors can happen, but what ones are actually a mystery.
        return ""
