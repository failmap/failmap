"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, Union

import pytz

from websecmap.reporting.models import ScanPolicy
from websecmap.reporting.policy import conclusion_to_score
from websecmap.scanners.scanmetadata import SCAN_TYPES_TO_SCANNER
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)


def get_score_from_policy(scan: Union[EndpointGenericScan, UrlGenericScan]) -> Dict[str, Any]:
    policy = conclusion_to_score(scan.type, scan.rating)
    data = strip_policy_data(policy)
    return standard_calculation(scan, **data)


def internet_nl(scan: Union[EndpointGenericScan, UrlGenericScan]) -> Dict[str, Any]:
    if "~" in scan.rating:
        # Used in old metrics
        _, scan_value = scan.rating.split("~")
        policy = conclusion_to_score(scan.type, scan_value)
    else:
        # New metrics are a lot simpler, let's hope it stays that way :)
        policy = conclusion_to_score(scan.type, scan.rating)

    data = strip_policy_data(policy)
    calc = standard_calculation(scan, **data)
    custom_fields = parse_internetnl_nl_explanation_data(scan)
    return {**calc, **custom_fields}


def strip_policy_data(policy: ScanPolicy) -> Dict[str, Any]:
    # Would it be smarter to just have the values we need?
    data = policy.__dict__
    data.pop("_state", None)
    data.pop("_foreign_key_cache", None)
    data.pop("annotation", None)
    data.pop("id", None)
    data.pop("total_issues", None)
    data.pop("ok", None)
    data.pop("scan_type", None)
    data.pop("conclusion", None)
    return data


def standard_calculation(
    scan: Union[EndpointGenericScan, UrlGenericScan],
    explanation: str,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    not_testable: bool = False,
    not_applicable: bool = False,
    error_in_test: bool = False,
) -> Dict[str, Any]:
    # Scan might be high, medium, low, whatever, but the policy decides what that means.

    ok = 0 if any([high, medium, low, not_testable, not_testable, error_in_test]) else 1  # pylint: disable=invalid-name

    return {
        "type": scan.type,
        "explanation": explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
        "ok": ok,
        "not_testable": not_testable,
        "not_applicable": not_applicable,
        "error_in_test": error_in_test,
    }


def parse_internetnl_nl_explanation_data(scan: EndpointGenericScan) -> Dict[str, Any]:
    custom_fields = {}

    # the explanation is a bunch of json, that is not really workable. These fields are split into separate data
    # and should be the same for everything except the score.

    # V1 reports do not have json stored in the explanation, only text messages or nothing.
    # So, only parse this is it contains json at all. To improve speed, first check the first letter.
    if scan.explanation and scan.explanation[0:1] == "{":
        try:
            data = json.loads(scan.explanation.strip())
            custom_fields["translation"] = data.get("translation", "")
            custom_fields["technical_details"] = scan.evidence
        except json.decoder.JSONDecodeError as exc:
            # not a json value, nothing is done with the explanation field otherwise
            log.debug(
                "explanation in internet.nl scan was not json compatible. Error: %s, Json: %s", exc, scan.explanation
            )

    # The original value contains more nuance than the agregation to high, medium and low. So use the translation but
    # also the original rating to show the correct icon. This is also used to determine the progression compared to
    # the previous scan. This nuance is important as good > good_not_tested.
    custom_fields["test_result"] = scan.rating

    return custom_fields


def get_severity(scan: Union[EndpointGenericScan, UrlGenericScan]) -> Dict[str, Any]:
    scanner = SCAN_TYPES_TO_SCANNER.get(scan.type, {"name": "dummy"})

    if scanner["name"] in ["internet_nl_mail", "internet_nl_web"]:
        calculation = internet_nl(scan)
    else:
        calculation = get_score_from_policy(scan)

    # handle comply or explain
    # only when an explanation is given AND the explanation is still valid when creating the report.
    calculation["is_explained"] = scan.comply_or_explain_is_explained
    calculation["comply_or_explain_explanation"] = scan.comply_or_explain_explanation
    if scan.comply_or_explain_explained_on:
        calculation["comply_or_explain_explained_on"] = scan.comply_or_explain_explained_on.isoformat()
    else:
        calculation["comply_or_explain_explained_on"] = ""

    if scan.comply_or_explain_explanation_valid_until:
        calculation[
            "comply_or_explain_explanation_valid_until"
        ] = scan.comply_or_explain_explanation_valid_until.isoformat()
    else:
        calculation["comply_or_explain_explanation_valid_until"] = ""

    valid = scan.comply_or_explain_is_explained and (
        scan.comply_or_explain_explanation_valid_until > datetime.now(pytz.utc)
    )
    calculation["comply_or_explain_valid_at_time_of_report"] = valid

    # tracking information for the scan (which also might allow upgrading the scan in the future)
    calculation["scan"] = scan.pk
    calculation["scan_type"] = scan.type

    return calculation
