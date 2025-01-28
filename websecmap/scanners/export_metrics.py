import itertools
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

import pyexcel
import tldextract
from django.conf import settings
from django.utils.text import slugify

import json
import re

from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.scanner.metric_constants import (
    WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT,
    WEB_PRIVACY_COOKIES_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_COOKIES_CRAWLED_WITH_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_REQUESTS,
    WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_WITH_CONSENT,
)
from websecmap.scanners.scanner.web_privacy import WEB_PRIVACY_COOKIES
from websecmap.scanners.scanner_for_everything.location import (
    SCAN_TYPE_LOCATION_COOKIES,
    SCAN_TYPE_LOCATION_MAIL_SERVER,
    SCAN_TYPE_LOCATION_SERVER,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITH_CONSENT,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITHOUT_CONSENT,
)
from websecmap.utils import normalize_cookie_name

log = logging.getLogger(__name__)


def export_current_metrics(
    layer: str = "central_government",
    scan_type: str = "web_privacy_cookies",
    rating: str = "web_privacy_cookies_neutral",
):
    epgs = EndpointGenericScan.objects.all().filter(
        is_the_latest_scan=True,
        endpoint__url__organization__is_dead=False,
        endpoint__url__organization__layers__name=layer,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__is_dead=False,
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


def create_pivot_data(scan_types: List[str], layers: List[str]) -> List[Dict[str, Any]]:
    product = []
    for scan_type in scan_types:
        print(f"Exporting {scan_type}")
        endpoint_scans = (
            EndpointGenericScan.objects.all()
            .filter(
                is_the_latest_scan=True,
                # when adding this, there are suddenly multiple scans of the same type...
                # sometimes even more than 2, while all data and associated information is not stored
                # in duplicates in the database. This is a bit mysterious.
                # will add a distinct because the carthesian layers will be added lateron still anyway...
                # endpoint__url__organization__is_dead=False,
                endpoint__url__is_dead=False,
                endpoint__url__not_resolvable=False,
                endpoint__is_dead=False,
                type=scan_type,
                # adding a distinct so we're sure its only one scan...
            )
            .distinct()
        )
        url_scans = (
            UrlGenericScan.objects.all()
            .filter(
                is_the_latest_scan=True,
                # same issue as above.
                # url__organization__is_dead=False,
                url__is_dead=False,
                url__not_resolvable=False,
                type=scan_type,
            )
            .distinct()
        )

        if layers:
            endpoint_scans = endpoint_scans.filter(endpoint__url__organization__layers__name__in=layers)
            url_scans = url_scans.filter(url__organization__layers__name__in=layers)

        # this somehow delivers an carthesian product but in the wrong way.
        # therefore filter manually if for this scan type

        for scan in list(endpoint_scans) + list(url_scans):
            pivot_records = determine_pivot_records(scan_type, scan)
            scan_data = {
                "scan_type": scan.type,
                "scan_rating": scan.rating,
                "scan_rating_determined_on": scan.rating_determined_on.isoformat(),
                "scan_last_scan_moment": scan.last_scan_moment.isoformat(),
                "is_explained": scan.comply_or_explain_is_explained,
            }
            endpoint_records = carthesian_product_for_scan(scan)
            for pivot_record in pivot_records:
                for endpoint_record in endpoint_records:
                    new_record = {**endpoint_record, **scan_data, **pivot_record}

                    # for some reason the stuff from other layers is still included.
                    if not layers or new_record["layer"] in layers:
                        product.append(new_record)
    return product


def export_pivot(scan_types: List[str], layers: List[str]) -> str:
    product = create_pivot_data(scan_types, layers)
    return save_pivot(product, file_name_hint=scan_types[0] if len(scan_types) == 1 else "")


def save_pivot(product: List[Dict[str, Any]], file_name_hint="") -> str:
    if file_name_hint:
        file_name_hint = f"{slugify(file_name_hint)}-"
    book = pyexcel.get_book(bookdict={"source": make_data_2d(product)})
    # save the book to the media root:
    os.makedirs(os.path.join(settings.MEDIA_ROOT, "pivot"), exist_ok=True)
    # random name prevents brute-forcing if the file has been uploaded somewhere
    filename = f"pivot/pivot-{file_name_hint}{datetime.now(timezone.utc).date()}-{uuid.uuid4()}.xlsx"
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
        SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITH_CONSENT,
        SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITHOUT_CONSENT,
    ]:
        return pivot_location_evidence(load_possible_json(scan.evidence))

    if scan_type in {"nuclei_exposed_panels"}:
        return pivot_nuclei_panel_evidence(scan.meaning)

    if scan_type in [
        WEB_PRIVACY_COOKIES,
        WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT,
        WEB_PRIVACY_COOKIES_CRAWLED_WITH_CONSENT,
        WEB_PRIVACY_COOKIES_CRAWLED_NO_CONSENT,
    ]:
        # as we're now using an extensive meaning, this meaning will now be pivoted instead of the normal
        # cookie records. This means the location and product are also loaded inside the export.
        # return pivot_cookies(load_possible_json(scan.evidence)) #  <-- this is the simple record without meaning.
        return pivot_cookie_meaning(load_possible_json(scan.evidence), scan.meaning)

    if scan_type in [
        WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_NO_CONSENT,
        WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_WITH_CONSENT,
        WEB_PRIVACY_THIRD_PARTY_REQUESTS,
    ]:
        # todo: should the location be added?
        # This is already a list of dicts.
        return pivot_generic_records(load_possible_json(scan.evidence))

    # if scan_type in [WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT]:
    #     # as we're now using an extensive meaning, this meaning will now be pivoted instead of the normal
    #     # cookie records. This means the location and product are also loaded inside the export.
    #     # return pivot_cookies(load_possible_json(scan.evidence)) #  <-- this is the simple record without meaning.
    #     return pivot_cookies_without_consent_meaning(load_possible_json(scan.evidence), scan.meaning)

    if scan_type in [SCAN_TYPE_LOCATION_COOKIES]:
        return pivot_cookie_locations(load_possible_json(scan.evidence))

    if scan_type in {"tls_qualys_certificate_trusted"}:
        return pivot_tls_qualys_certificate_trusted(load_possible_json(scan.evidence))

    # direct scan data in evidence, nothing else
    if scan_type in {"bannergrab"}:
        return [{"banner": scan.evidence}]

    if load_possible_json(scan.evidence):
        # assume this is a single dict, and not a list of dicts...
        return pivot_generic_records([load_possible_json(scan.evidence)])

    # return at least one record, so everything can be pivoted even if there is no specialized evidence.
    # todo: you can at least split up rating determined on in day, month and year.
    log.error(scan_type)
    return [{"default": 1}]


def load_possible_json(data):
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return []


def pivot_products(evidence):
    return [pivot_product_record(row) for row in evidence]


def pivot_cookies(evidence) -> List[Dict[str, Any]]:
    # Cookies are already a flat object. But we'll add a cookie_ prefix to better identify them:
    # currently the value is not stored as it's usually random and causes a lot of data
    return [pivot_cookie_record(row) for row in evidence]


def pivot_cookie_meaning(evidence_records: List[Dict[str, Any]], meaning: Dict[str, Any]) -> List[Dict[str, Any]]:
    # are 100% of all cookies processed in this export? What if there is no product and / or no location?
    # how are these matched
    pivot_records = []

    for cookie in evidence_records:
        p_cookie = pivot_cookie_record(cookie)
        # start out with empty records, so all keys are present
        p_product = pivot_product_record({})
        p_location = pivot_location_record({})

        # see in what product and location this is in
        for product in meaning.get("products", []):
            for product_cookie in product["cookies"]:
                if cookies_are_equal(cookie, product_cookie):
                    # this specific cookie is a match, so lets see the additional stuff if its there...
                    z = cookie_indicator_data(product_cookie)
                    p_cookie["cookie_indicator"] = z["cookie_indicator"]
                    p_cookie["cookie_purpose"] = z["cookie_purpose"]
                    p_cookie["cookie_purpose_rating"] = z["cookie_purpose_rating"]
                    p_product = pivot_product_record(product)
                    continue

        for location in meaning.get("locations", []):
            for location_cookie in location["applicable_cookies"]:
                if cookies_are_equal(cookie, location_cookie):
                    p_location = pivot_location_record(location)
                    continue

        pivot_records.append({**p_cookie, **p_product, **p_location})

    return pivot_records


def cookies_are_equal(cookie_a: Dict[str, Any], cookie_b: Dict[str, Any]):
    if cookie_a["name"] != cookie_b["name"]:
        return False

    if cookie_a["domain"] != cookie_b["domain"]:
        return False

    if cookie_a["path"] != cookie_b["path"]:
        return False

    # We're ignoring httpOnly, secure, sameSite etc... this combo should be enough to be the key.

    return True


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


def pivot_nuclei_panel_evidence(evidence: Dict[str, Any]):
    """
    {'tech': [{'portal_name': 'phpMyAdmin Panel', 'portal_url':
    'https://pop.andrema39.thirtynine.axc.nl:443/phpMyAdmin/', 'portal_extracted': ['5.2.1'], 'tech':
    [{'product': 28, 'version': '5.2.1'}, {'product': 1, 'version': 'unknown'}, {'product': 172, 'version': '2'},
    {'product': 35, 'version': 'unknown'}, {'product': 43, 'version': 'unknown'}]}]}

    """

    # there is some malformed data in the database, in that situation just return no pivot results.
    if evidence == "{}":
        return []

    if isinstance(evidence, str):
        return []

    techs = evidence.get("tech", [])
    # prevent ValueError: Cannot convert [] to Excel.
    for tech in techs:
        tech["portal_extracted"] = " ".join(tech.get("portal_extracted", []))
        # don't add the entire series of products, those are a lot of records.
        tech["tech"] = None

    return techs


def pivot_generic_records(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Input:
    [
        {
            "method": "GET",
            "resource_type": "script",
            "url": "cdn-eu.readspeaker.com",
            "post_data": ""
            # not all of them have a count
            "count": 1
        },
        ...
    ]
    """
    return evidence


def pivot_product_record(record) -> Dict[str, Any]:
    return {
        "product_id": record.get("product_id", 0),
        "product_name": record.get("product_name", ""),
        "product_version": record.get("product_version", ""),
        "product_vendor_name": record.get("product_vendor_name", ""),
        "product_vendor_id": record.get("product_vendor_id", 0),
    }


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
        "location_rating": record.get("rating"),
        "location_continent_code": record.get("evidence", {}).get("found_location", {}).get("continent_code", ""),
        "location_country_iso_code": record.get("evidence", {}).get("found_location", {}).get("country_iso_code", ""),
        "location_city_in_en": record.get("evidence", {}).get("found_location", {}).get("city_in_en", ""),
        "location_as_number": record.get("evidence", {}).get("found_location", {}).get("as_number", -1),
        "location_as_organization": record.get("evidence", {}).get("found_location", {}).get("as_organization", ""),
        "location_isp_ame": record.get("evidence", {}).get("found_location", {}).get("isp_ame", ""),
        "location_network": record.get("evidence", {}).get("found_location", {}).get("network", ""),
        "location_country_rating": record.get("evidence", {}).get("country_rating", ""),
        "location_continent_rating": record.get("evidence", {}).get("continent_rating", ""),
        "location_domain": record.get("domain", ""),
        "location_priority": record.get("priority", ""),
    }


def hash_cookie_record(record) -> str:
    # {"name": "ARRAffinity", "domain": ".workforce-adhocplanner-rc.ortecapps.com", "path": "/", "httpOnly": True,
    #          "secure": True, "sameSite": "Lax"}

    return (
        f"{record['name']}-"
        f"{record['domain']}-{record['path']}-{record['httpOnly']}-{record['secure']}-{record['sameSite']}"
    )


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
        # make results consistent
        "cookie_indicator": 0,
        "cookie_purpose": "",
        "cookie_purpose_rating": "",
    }


def is_nth_bit_set(x: int, n: int) -> bool:
    return bool(x & (1 << n))


def parse_issuer_subject(data: str) -> Dict[str, Any]:
    """
    This is a RFC4514 string. Not going to ship the ldap3 library for this.

    Issuer is a sting like this: "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
    it can have all kinds of fields, let's get the most common ones: CN, O, C

    Other examples:

    https://stackoverflow.com/questions/6464129/certificate-subject-x-509

    We want: CN, O, C, OU, L, ST
    """
    fields = re.findall(r"[A-Z]*=", data)
    found_data = {}

    for index, field in enumerate(fields):
        fieldname = field.replace("=", "")
        # use this field up until the next one
        if index != len(fields) - 1:
            pattern = rf"({fields[index]})(.*), ({fields[index+1]})"
            results = re.findall(pattern, data)
            if results and len(results[0]) > 1:
                found_data[fieldname] = re.findall(pattern, data)[0][1]
            else:
                found_data[fieldname] = ""

        else:
            # the last field is just the rest of the data.
            pattern = rf"{fields[len(fields) -1]}(.*)"
            result = re.findall(pattern, data)
            found_data[fieldname] = re.findall(pattern, data)[0] if result else ""

    return {
        "C": found_data.get("C", ""),
        "O": found_data.get("O", ""),
        "OU": found_data.get("OU", ""),
        "Q": found_data.get("Q", ""),
        "ST": found_data.get("ST", ""),
        "L": found_data.get("L", ""),
        "CN": found_data.get("CN", ""),
        # this is to find Organizational Verified domains.
        "businessCategory": found_data.get("businessCategory", ""),
        "SERIALNUMBER": found_data.get("SERIALNUMBER", ""),
    }


def pivot_tls_qualys_certificate_trusted(records):
    """
    https://github.com/ssllabs/ssllabs-scan/blob/master/ssllabs-api-docs-v3.md

    [
      {
        "subject": "CN=academie.scopescholen.nl",
        "commonNames": [
          "academie.scopescholen.nl"
        ],
        "altNames": [
          "academie.scopescholen.nl"
        ],
        "notBefore": 1710875488000,
        "notAfter": 1718651487000,
        "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
        "issuerLabel": "R3",
        "sigAlg": "SHA256withRSA",
        "revocationInfo": 2,
        "crlURIs": [
          ""
        ],
        "ocspURIs": [
          "http://r3.o.lencr.org"
        ],
        "revocationStatus": 2,
        "crlRevocationStatus": 4,
        "ocspRevocationStatus": 2,
        "sgc": 0,
        "issues": 9,
        "sct": true,
        "mustStaple": 0,
        "sha1Hash": "32ca92c8e9d19ea6ead97ef91a58efb507dcddcc",
        "pinSha256": "lntwaDy8uxvFW3DEW6/5X5jquckJj+F+rjCNv1Dve9Q=sigAlg"
      }
    ]

    There are many convoluted fields in this data.
    """

    if records:
        first_row = records[0]
    else:
        return []

    issues = first_row.get("issues", -1)
    sgc = first_row.get("sgc", 0)
    # subject on cert: politie.nl
    parsed_subject = parse_issuer_subject(first_row.get("subject", ""))
    # issuer details, like: QuoVadis Trustlink B.V.
    issuerSubject = first_row.get("issuerSubject", "")
    parsed_issuerSubject = parse_issuer_subject(issuerSubject)

    validation = "Domain"
    if parsed_subject["SERIALNUMBER"]:
        validation = "Organization"
    if first_row.get("validationType", "N") == "E":
        validation = "Extended"

    return [
        {
            # plain export of values without any normalization
            "subject": first_row.get("subject", ""),
            "commonNames": ",".join(first_row.get("commonNames", [])),
            "altNames": ",".join(first_row.get("altNames", [])),
            "notBefore": first_row.get("notBefore", 0),
            "notAfter": first_row.get("notAfter", 0),
            "issuerSubject": first_row.get("issuerSubject", ""),
            "issuerLabel": first_row.get("issuerLabel", ""),
            "sigAlg": first_row.get("sigAlg", ""),
            "revocationInfo": first_row.get("revocationInfo", 0),
            # these fields cause 50% of the data for no added value in filtering etc
            # "crlURIs": ",".join(first_row.get("crlURIs", [])),
            # "ocspURIs": ",".join(first_row.get("ocspURIs", [])),
            "revocationStatus": first_row.get("revocationStatus", 0),
            "crlRevocationStatus": first_row.get("crlRevocationStatus", 0),
            "ocspRevocationStatus": first_row.get("ocspRevocationStatus", 0),
            "sgc": first_row.get("sgc", 0),
            "issues": first_row.get("issues", 0),
            "sct": first_row.get("sct", False),
            "mustStaple": first_row.get("mustStaple", 0),
            "sha1Hash": first_row.get("sha1Hash", ""),
            "pinSha256": first_row.get("pinSha256", ""),
            # optional fields: N for normal
            "validationType": first_row.get("validationType", "N"),
            # revocation split out into several fields, which makes filtering nicer
            # """
            # 0 - not checked
            # 1 - certificate revoked
            # 2 - certificate not revoked
            # 3 - revocation check error
            # 4 - no revocation information
            # 5 - internal error
            # """
            "revocation_not_checked": first_row.get("revocationStatus", -1) == 0,
            "revocation_revoked": first_row.get("revocationStatus", -1) == 1,
            "revocation_not_revoked": first_row.get("revocationStatus", -1) == 2,
            "revocation_check_error": first_row.get("revocationStatus", -1) == 3,
            "revocation_no_revocation_information": first_row.get("revocationStatus", -1) == 4,
            "revocation_internal_error": first_row.get("revocationStatus", -1) == 5,
            # """
            # sgc - Server Gated Cryptography support; integer:
            # bit 1 (1) - Netscape SGC
            # bit 2 (2) - Microsoft SGC
            # """
            "sgc_netscape": is_nth_bit_set(sgc, 1),
            "sgc_microsoft": is_nth_bit_set(sgc, 2),
            # """
            # issues - list of certificate issues, one bit per issue:
            # bit 0 (1) - no chain of trust
            # bit 1 (2) - not before
            # bit 2 (4) - not after
            # bit 3 (8) - hostname mismatch
            # bit 4 (16) - revoked
            # bit 5 (32) - bad common name
            # bit 6 (64) - self-signed
            # bit 7 (128) - blacklisted
            # bit 8 (256) - insecure signature
            # bit 9 (512) - insecure key
            # """
            "issues_no_chain_of_trust": is_nth_bit_set(issues, 1),
            "issues_not_before": is_nth_bit_set(issues, 2),
            "issues_not_after": is_nth_bit_set(issues, 3),
            "issues_hostname_mismatch": is_nth_bit_set(issues, 4),
            "issues_revoked": is_nth_bit_set(issues, 5),
            "issues_bad_common_name": is_nth_bit_set(issues, 6),
            "issues_self_signed": is_nth_bit_set(issues, 7),
            "issues_blacklisted": is_nth_bit_set(issues, 8),
            "issues_insecure_signature": is_nth_bit_set(issues, 1),
            "issues_insecure_key": is_nth_bit_set(issues, 9),
            # """
            # Issuer is a sting like this: "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
            # it can have all kinds of fields, let's get the most common ones: CN, O, C
            # """
            "issuerSubject_country": parsed_issuerSubject["C"],
            "issuerSubject_organization": parsed_issuerSubject["O"],
            "issuerSubject_organizational_unit": parsed_issuerSubject["OU"],
            "issuerSubject_name_qualifier": parsed_issuerSubject["Q"],
            "issuerSubject_state": parsed_issuerSubject["ST"],
            "issuerSubject_common_name": parsed_issuerSubject["CN"],
            "issuerSubject_locality": parsed_issuerSubject["L"],
            # subject data is available at more expensive certificates, like 'organization' validated.
            "subject_organization": parsed_subject["O"],
            "subject_locality": parsed_subject["L"],
            "subject_serialnumber": parsed_subject["SERIALNUMBER"],
            "subject_businessCategory": parsed_subject["businessCategory"],
            "validation": validation,
        }
    ]


def cookie_indicator_data(record):
    return {
        "cookie_indicator": record.get("indicator", 0),
        "cookie_purpose": record.get("purpose", ""),
        "cookie_purpose_rating": record.get("purpose_rating", ""),
    }


def web_privacy_cookie_products_no_consent_record(record):
    # using ... without any comments creates two statements on a single line which is not like by other linters.
    ...
