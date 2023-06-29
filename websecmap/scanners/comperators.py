# helps filtering differences in evidence between findings.
from typing import Any, List, Dict
from urllib.parse import parse_qs, urlparse

from websecmap.app import log


def compare_web_privacy_third_party_requests(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> bool:
    if len(old) != len(new):
        return False

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
        log.debug(f"failed to compare urls: {old} vs {new}: {e}")
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

        log.debug(f"keys_old_data: {keys_old_data}")

        return keys_old_data == keys_new_data
    except Exception as e:
        log.debug(f"failed to compare qsl keys: {old} vs {new}: {e}")
        return False
