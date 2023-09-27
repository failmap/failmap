import itertools
from datetime import datetime, timezone
from typing import List, Union, Any, Dict

import tldextract
from django.conf import settings
import os
import uuid

import pyexcel

from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
import json

from websecmap.scanners.scanner.web_privacy import WEB_PRIVACY_COOKIES
from websecmap.scanners.scanner_for_everything.location import (
    SCAN_TYPE_LOCATION_MAIL_SERVER,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT,
    SCAN_TYPE_LOCATION_SERVER,
    SCAN_TYPE_LOCATION_COOKIES,
)
from websecmap.utils import normalize_cookie_name


def export_current_metrics(
    layer: str = "central_government",
    scan_type: str = "web_privacy_cookies",
    rating: str = "web_privacy_cookies_neutral",
):
    epgs = EndpointGenericScan.objects.all().filter(
        is_the_latest_scan=True,
        endpoint__url__organization__layers__name=layer,
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        rating=rating,
        type=scan_type,
    )
    data = []
    for epg in epgs:
        record = {
            "endpoint": str(epg.endpoint),
            "url": str(epg.endpoint.url),
            "endpoint_id": epg.endpoint.id,
            "url_id": epg.endpoint.url.id,
            "rating": epg.rating,
            "type": epg.type,
            # 'layer': epg.endpoint.url.organization.layers.name,
            "evidence": epg.evidence,
        }
        data.append(record)
    print(json.dumps(data, indent=4))


def export_pivot(scan_types: List[str]) -> str:
    product = []
    for scan_type in scan_types:
        endpoint_scans = list(EndpointGenericScan.objects.all().filter(is_the_latest_scan=True, type=scan_type))
        url_scans = list(UrlGenericScan.objects.all().filter(is_the_latest_scan=True, type=scan_type))
        for scan in endpoint_scans + url_scans:
            pivot_records = determine_pivot_records(scan_type, scan)
            scan_data = {
                "scan_type": scan.type,
                "scan_rating": scan.rating,
                "scan_rating_determined_on": scan.rating_determined_on.isoformat(),
                "is_explained": scan.comply_or_explain_is_explained,
            }
            endpoint_records = carthesian_product_for_scan(scan)
            for pivot_record in pivot_records:
                for endpoint_record in endpoint_records:
                    # the endpoint record ends with arbitrary KV data, which might differ per record
                    new_record = {**endpoint_record, **scan_data, **pivot_record}
                    product.append(new_record)

    return save_pivot(product)


def save_pivot(product: List[Dict[str, Any]]) -> str:
    book = pyexcel.get_book(bookdict={"source": make_data_2d(product)})
    # save the book to the media root:
    os.makedirs(os.path.join(settings.MEDIA_ROOT, "pivot"), exist_ok=True)
    # random name prevents brute-forcing if the file has been uploaded somewhere
    filename = f"pivot/pivot-{datetime.now(timezone.utc).date()}-{uuid.uuid4()}.xlsx"
    book.save_as(filename=os.path.join(settings.MEDIA_ROOT, filename))
    return filename


def make_data_2d(data: List[Dict[str, Any]]) -> List[List[str]]:
    # Not all objects have the same columns, so here we collect all columns to know what columns would be missing
    # from other objects. This helps with creating a 'spreadsheet' file where all data has to be present.
    # all the same columns should end up in the same place, even if they are empty.
    # the order is relevant because it makes the data easier to understand!
    all_columns: List[str] = []
    for record in data:
        for key in record.keys():
            if key not in all_columns:
                all_columns.append(key)

    # now add the missing columns in every record, including the first record ofc:
    for record, column in itertools.product(data, all_columns):
        if column not in record.keys():
            record[column] = None

    # now sort the columns so they are all in the same place, like a two-d thing is
    # use custom order that matches the order in all_columns
    # output is a list of lists, all are values, so no kv.
    output: List[List[str]] = [all_columns]
    for record in data:
        sorted_record = [record[column] for column in all_columns]
        output.append(sorted_record)

    return output


def carthesian_product_for_scan(scan: Union[EndpointGenericScan, UrlGenericScan]):
    # find associated url, possible multiple organizations and multiple maps this can be on. Return this as a list.

    if isinstance(scan, EndpointGenericScan):
        query = (
            [scan.endpoint.url]
            if scan.endpoint.url.is_dead is False and scan.endpoint.url.not_resolvable is False
            else []
        )
    else:
        query = [scan.url] if scan.url.is_dead is False and scan.url.not_resolvable is False else []

    product = []
    for url in query:
        for organization in url.organization.all().filter(is_dead=False):
            for layer in organization.layers.all():
                new_record = {
                    "layer": layer.name,
                    "organization_name": organization.name,
                    "organization_id": organization.id,
                    "organization_country": organization.country.code,
                    "url": url.url,
                    "computed_subdomain": url.computed_subdomain,
                    "computed_domain": url.computed_domain,
                    "computed_suffix": url.computed_suffix,
                }

                if isinstance(scan, EndpointGenericScan):
                    new_record["endpoint_protocol"] = scan.endpoint.protocol
                    new_record["endpoint_port"] = scan.endpoint.port
                    new_record["endpoint_ip_version"] = scan.endpoint.ip_version
                else:
                    new_record["endpoint_protocol"] = None
                    new_record["endpoint_port"] = None
                    new_record["endpoint_ip_version"] = None

                arbitrary_data = organization.arbitrary_kv_data
                for key, value in arbitrary_data.items():
                    new_record[f"organization_{key}"] = value

                product.append(new_record)
    return product


def determine_pivot_records(scan_type: str, scan) -> List[dict[str, Any]]:
    if scan_type in [
        SCAN_TYPE_LOCATION_SERVER,
        SCAN_TYPE_LOCATION_MAIL_SERVER,
        SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT,
    ]:
        return pivot_location_evidence(load_possible_json(scan.evidence))

    if scan_type in [WEB_PRIVACY_COOKIES]:
        return pivot_cookies(load_possible_json(scan.evidence))

    if scan_type in [SCAN_TYPE_LOCATION_COOKIES]:
        return pivot_cookie_locations(load_possible_json(scan.evidence))

    return []


def load_possible_json(data):
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return []


def pivot_cookies(evidence) -> List[Dict[str, Any]]:
    # Cookies are already a flat object. But we'll add a cookie_ prefix to better identify them:
    # currently the value is not stored as it's usually random and causes a lot of data
    return [pivot_cookie_record(row) for row in evidence]


def pivot_location_evidence(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [pivot_location_record(record) for record in evidence]


def pivot_cookie_locations(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # This mixes cookie AND location which needs to be exported to a flat list...
    #
    """
    [
      {
        "rating": "location_ok",
        "evidence": {
          "found_location": {
            "continent_code": "EU",
            "country_iso_code": "NL",
            "city_in_en": "",
            "as_number": 43366,
            "as_organization": "OSSO B.V.",
            "isp_ame": "OSSO B.V.",
            "network": "195.28.22.0/23"
          },
          "country_rating": "unknown",
          "continent_rating": "ok"
        },
        "domain": "intranet-acc.landvancuijk.nl",
        "applicable_cookies": [
          {
            "name": "OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
            "domain": "intranet-acc.landvancuijk.nl",
            "path": "/",
            "httpOnly": true,
            "secure": true,
            "sameSite": "None"
          }
        ]
      },
      ...
    ]
    """
    per_cookie_record = []
    for row in evidence:
        per_location_record = pivot_location_record(row)
        for cookie in row["applicable_cookies"]:
            cr = pivot_cookie_record(cookie)
            per_cookie_record.append({**per_location_record, **cr})
    return per_cookie_record


def pivot_location_record(record) -> Dict[str, Any]:
    """
    Convert
      {
        "rating": "location_medium",
        "evidence": {
          "found_location": {
            "continent_code": "NA",
            "country_iso_code": "US",
            "city_in_en": "Kansas City",
            "as_number": 396982,
            "as_organization": "GOOGLE-CLOUD-PLATFORM",
            "isp_ame": "Google Cloud",
            "network": "34.98.64.0/18"
          },
          "country_rating": "medium",
          "continent_rating": "medium"
        },
        "domain": "app-script.monsido.com"
      },

    To a flat object:
      {
        "rating": "location_medium",
        "continent_code": "NA",
        "country_iso_code": "US",
        "city_in_en": "Kansas City",
        "as_number": 396982,
        "as_organization": "GOOGLE-CLOUD-PLATFORM",
        "isp_ame": "Google Cloud",
        "network": "34.98.64.0/18",
        "country_rating": "medium",
        "continent_rating": "medium",
        "domain": "app-script.monsido.com"
      },
    """
    return {
        "rating": record.get("rating"),
        "continent_code": record.get("evidence", {}).get("found_location", {}).get("continent_code", ""),
        "country_iso_code": record.get("evidence", {}).get("found_location", {}).get("country_iso_code", ""),
        "city_in_en": record.get("evidence", {}).get("found_location", {}).get("city_in_en", ""),
        "as_number": record.get("evidence", {}).get("found_location", {}).get("as_number", -1),
        "as_organization": record.get("evidence", {}).get("found_location", {}).get("as_organization", ""),
        "isp_ame": record.get("evidence", {}).get("found_location", {}).get("isp_ame", ""),
        "network": record.get("evidence", {}).get("found_location", {}).get("network", ""),
        "country_rating": record.get("evidence", {}).get("country_rating", ""),
        "continent_rating": record.get("evidence", {}).get("continent_rating", ""),
        "domain": record.get("domain", ""),
        "priority": record.get("priority", ""),
    }


def pivot_cookie_record(record) -> Dict[str, Any]:
    """
    [
      {
        "name": "ClientId",
        "domain": "outlook.office365.com",
        "path": "/",
        "httpOnly": false,
        "secure": true,
        "sameSite": "None"
      },
      ...

    to:
        [
      {
        "cookie_name": "ClientId",
        "cookie_domain": "outlook.office365.com",
        "cookie_path": "/",
        "cookie_httpOnly": false,
        "cookie_secure": true,
        "cookie_sameSite": "None"
      },
      ...

    """
    extract = tldextract.extract(record["domain"])

    return {
        # the well known fields of cookies
        "cookie_name": record["name"],
        "cookie_name_normalized": normalize_cookie_name(record["name"]),
        "cookie_domain": record["domain"],
        "cookie_path": record["path"],
        "cookie_httpOnly": record["httpOnly"],
        "cookie_secure": record["secure"],
        "cookie_sameSite": record["sameSite"],
        # there can be patterns in subdomains as well
        # and perhaps this information might be junk?
        "cookie_parsed_subdomain": extract.subdomain,
        "cookie_parsed_domain": extract.domain,
        "cookie_parsed_domainsuffix": extract.suffix,
        "cookie_parsed_fqdn": extract.fqdn,
    }
