# helps filtering differences in evidence between findings.
from collections import defaultdict
from typing import Any, List, Dict
from urllib.parse import parse_qs, urlparse
import json
from pprint import pprint

import tldextract

from websecmap.app import log
from websecmap.reporting import time_cache
from websecmap.scanners.models import EndpointGenericScan, UrlReduction
from websecmap.scanners.scanner.security_headers import remove_guid_from_string, remove_timestamp_from_end_of_string


def web_privacy_third_party_requests_equal(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> bool:
    if len(old) != len(new):
        return False

    # todo: does it matter to sort by url?
    # todo: have the requests been normalized/reduced? Where should that have happened? As all those id's and stuff
    #  also happen in csp metrics

    return all(third_party_request_is_present(new_item, old) for new_item in new)


def third_party_request_is_present(single_third_party_request: Dict[str, Any], ltpr: List[Dict[str, Any]]) -> bool:
    for ltpr_item in ltpr:
        # slowly build a match with increasingly complex filters, so to keep this somewhat fastish
        if ltpr_item["method"] != single_third_party_request["method"]:
            continue

        if ltpr_item["resource_type"] != single_third_party_request["resource_type"]:
            continue

        # post data is somewhat rare, so compare that earlier than urls, as urls are mostly complex
        if not compare_qsl_keys(ltpr_item["post_data"], single_third_party_request["post_data"]):
            continue

        if not compare_urls(ltpr_item["url"], single_third_party_request["url"]):
            continue

        # you did it, an exact match!
        return True

    return False


def compare_urls(old: str, new: str) -> bool:
    try:
        parsed_old = urlparse(old)
        parsed_new = urlparse(new)

        # should have at least a scheme and address, the rest might be whatever
        if not parsed_old.scheme or not parsed_old.netloc or not parsed_new.scheme or not parsed_new.netloc:
            return False

        if parsed_old.scheme != parsed_new.scheme:
            # log.debug(f"scheme mismatch: {old} vs {new}")
            return False

        if parsed_old.netloc != parsed_new.netloc:
            # log.debug(f"netloc mismatch: {old} vs {new}")
            return False

        if parsed_old.path != parsed_new.path:
            # log.debug(f"path mismatch: {old} vs {new}")
            return False

        return compare_qsl_keys(parsed_old.query, parsed_new.query)
    except Exception as e:
        # we're testing all types of data, including bytes, so this is needed to avoid a crash in logging
        # normal logging does NOT work
        log.debug(f"failed to compare urls: {old} vs {new}: {e}")  # pylint: disable=logging-fstring-interpolation
        return False


def compare_qsl_keys(old: str, new: str) -> bool:
    # shortcut if they are identical anyway, saving some time
    try:
        if old == new:
            return True

        # post data is urlencoded, so decode it and then split it into a list of parameters
        old_data = parse_qs(old, keep_blank_values=True)
        new_data = parse_qs(new, keep_blank_values=True)

        keys_old_data = list(sorted(old_data.keys()))
        keys_new_data = list(sorted(new_data.keys()))

        log.debug("keys_old_data: %s", keys_old_data)

        return keys_old_data == keys_new_data
    except Exception as e:
        # we're testing all types of data, including bytes, so this is needed to avoid a crash in logging
        # normal logging does NOT work
        log.debug(f"failed to compare urls: {old} vs {new}: {e}")  # pylint: disable=logging-fstring-interpolation
        return False


def get_reductions():
    # this could be abstracted
    # time_cache the result to speed up the process over large amounts of data, idk how fast this really is...

    if my_cached := time_cache.cache_get("url_reductions"):
        return my_cached

    reductions = {
        "start": {},
        "end": {},
        "center": {},
    }

    reduction_data = UrlReduction.objects.all().only("search_for", "search_location", "replace_with")
    for reduction in reduction_data:
        if reduction.search_location not in reductions:
            log.error("Url Reduction %s has no valid search_location", reduction.id)
            continue
        reductions[reduction.search_location][reduction.search_for] = reduction.replace_with

    if reductions:
        time_cache.cache_set("url_reductions", reductions)

    return reductions


def remove_known_random_content_from_url(url: str) -> str:
    # todo: add to help-text on this metric that TOKEN, TIMESTAMP and GUID are replacements as these indicators
    #  change every request. These are usually session tokens, CDN tokens, anti-caching tokens, client-id's and so on.
    #  The metric is as complete as possible on stable data, but live-changing data per request is reduced. This
    #  metric is as informative as possible.

    url = remove_guid_from_string(url)
    # don't know if this adds too much, just a few sites use this but it's a regex on all data...
    url = remove_timestamp_from_end_of_string(url)

    reductions = get_reductions()
    for reduction, replacement in reductions["start"].items():
        # don't use regex, that is just too slow and these urls are identified with the start anyway
        if url.startswith(reduction):
            url = replacement
    for reduction, replacement in reductions["end"].items():
        if url.endswith(reduction):
            url = replacement
    for reduction, replacement in reductions["center"].items():
        if reduction in url:
            url = replacement
    return url


def remove_randomization_from_url(url: str) -> str:
    """
    todo: move this method to the appropriate location

    Removes values from the query strings, using only keys in alphabetical order.
    Removes randomization from the url from known random content. This list is never complete(!)
    Guids will be changed to GUID
    """
    url = remove_known_random_content_from_url(url)
    parsed = urlparse(url)
    # empty and order params
    params = list(sorted(parse_qs(parsed.query, keep_blank_values=True).keys()))
    if not params:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{'&'.join(params)}"


def gather_url_from_live_data(amount: int = 1000):
    # with this method it will be pretty easy to see what has random data and what is pretty stable, especially
    # when running this over a large number of records. 1 call and tons of random numbers means unstable data.
    scans = (
        EndpointGenericScan.objects.all()
        .filter(type="web_privacy_third_party_requests")
        .only("id", "evidence")[:amount]
    )
    urls = defaultdict(dict)
    for scan in scans:
        if not scan.evidence:
            continue
        try:
            evidence = json.loads(scan.evidence)
        except json.JSONDecodeError:
            continue
        for item in evidence:
            extract = tldextract.extract(item["url"])
            normalized_url = remove_randomization_from_url(item["url"])
            if normalized_url not in urls[f"{extract.domain}.{extract.suffix}"]:
                # seen once
                urls[f"{extract.domain}.{extract.suffix}"][normalized_url] = 1
            else:
                # seen more often
                urls[f"{extract.domain}.{extract.suffix}"][normalized_url] += 1
    # we can remove everything where the count > 1, as that are 'more static' resources
    for site_content in urls.values():
        for url, count in list(site_content.items()):
            if count > 1:
                del site_content[url]
    pprint(urls)
    # and calculate the number of unique urls divided by the number of times seen. The closer the number is to 1,
    # the less stable the data is, as that only contains unique urls. This number only works on very large datasets!
    ratio = []
    for domain, site_content in urls.items():
        # this might have been removed as we only filter on 1
        if not site_content:
            continue
        urls = len(site_content)
        counts = sum(count for url, count in site_content.items())
        ratio.append({"domain": domain, "urls": urls, "counts": counts, "ratio": urls / counts})
    # sort by counts
    ratio = sorted(ratio, key=lambda item: item["counts"], reverse=True)
    pprint(ratio)
