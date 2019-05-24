import logging

from urllib3.exceptions import HTTPError
from wikidata.client import Client

log = logging.getLogger(__package__)


OFFICIAL_WEBSITE: str = "P856"
ISO3316_2_COUNTRY_CODE: str = "P297"


def get_property_from_code(wikidata_code: str, property_code: str):
    """
    Note: this is very inefficient at getting multiple properties.

    :param wikidata_code: Q9928
    :param property_code: P856
    :return:
    """
    try:
        client = Client()

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
