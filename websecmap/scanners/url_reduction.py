# helps filtering differences in evidence between findings.
from collections import defaultdict
from urllib.parse import parse_qs, urlparse
import json
from pprint import pprint

import tldextract

from websecmap.app import log
from websecmap.reporting import time_cache
from websecmap.scanners.models import EndpointGenericScan, UrlReduction
from websecmap.scanners.scanner.security_headers import remove_guid_from_string, remove_timestamp_from_end_of_string


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


def gather_urls_from_web_privacy_third_party_requests(amount: int = 1000):
    """
    This is a function that helps build a catalog of all urls that contains unique random values such as
     timestamps, guids, tracking-id's, session values and what not. This can by run by hand to get a list of
     urls that only are seen once in the database. From that list the new UrlReductions can be crafted by hand.
     This is a manual proced that needs to happen once every year or so, just to reduce the number of records
     created in the database with useless values.
    """
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
    # below ratio is very uninteresting when everything above N=1 is culled
    # and calculate the number of unique urls divided by the number of times seen. The closer the number is to 1,
    # the less stable the data is, as that only contains unique urls. This number only works on very large datasets!
    # ratio = []
    # for domain, site_content in urls.items():
    #     # this might have been removed as we only filter on 1
    #     if not site_content:
    #         continue
    #     urls = len(site_content)
    #     counts = sum(count for url, count in site_content.items())
    #     ratio.append({"domain": domain, "urls": urls, "counts": counts, "ratio": urls / counts})
    # # sort by counts
    # ratio = sorted(ratio, key=lambda item: item["counts"], reverse=True)
    # pprint(ratio)
