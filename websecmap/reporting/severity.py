"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import json
import logging
from datetime import datetime
from typing import Union, Any, Dict

import pytz

from websecmap.reporting.models import ScanPolicy
from websecmap.reporting.policy import conclusion_to_score
from websecmap.scanners import SCAN_TYPES_TO_SCANNER
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)


def http_security_headers(scan: Union[EndpointGenericScan, UrlGenericScan]):
    """
    Rationale for classifcation

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
        # prevents reflected xss
        'X-XSS-Protection'
        Classified as: Medium

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
        # prevents clickjacking
        'X-Frame-Options':
        Classified as: High

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options
        # forces the content-type to be leading for defining a type of file (not the browser guess)
        # The browser guess could execute the file, for example with the wrong plugin.
        # Basically the server admin should fix the browser, instead of the other way around.
        'X-Content-Type-Options':
        Classified as: Low

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
        # Will be the browser default. Forces https, even if http resources are available.
        #
        # The preload list is idiotic: it should contain any site in the world.
        # A whopping 1 municipality in NL uses the preload list (eg knows if it's existence).
        # preload list is obscure and a dirty fix for a structural problem.
        #
        # Another weird thing is: the default / recommendation for hsts is off. Many sites, esp. in
        # governments have a once-a-year cycle for doing something requires. So HSTS should be
        # longer than a year, like one year and three months. Some site punish long hsts times.
        'Strict-Transport-Security':
        Classified as: High

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Public-Key-Pins
        # Has the potential to make your site unreachable if not properly (automatically) maintained
        # The backup cert strategy is also incredibly complex. Creating the right hash is also hard.
        # So if you don't use this. There should be another way to link the content of the site to
        # the transport.
        # header likely to be killed like p3p
        'Public-Key-Pins': 0,
        Classified as: Ignored

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
        # Very complex header to specify what resources can be loaded from where. Especially useful
        # when loading in third party content such as horrible ads. Prevents against xss
        'Content-Security-Policy':
        Classified as: Low

        # Flash, PDF and other exploit prone things can be embedded. Should never happen:
        # the content should always be none(?).
        # if not set to none, it is 200 points for allowing flash and pdf to be embedded at all :)
        'X-Permitted-Cross-Domain-Policies':
        Classified as: Ignored

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy
        # largely unsupported
        # What referrer should be allowed to access the resource. Security on referrer headers? No.
        'Referrer-Policy':
        Classified as: Ignored
        todo: should be enabled(?)

        todo: we're going to need to split this up per header, there are too many code paths forming.
    """
    # This function only exists to translate abstracts conclusions to a bit more verbose conclusions

    # We add what is done well, so it's more obvious it's checked.
    if scan.rating == "Unreachable":
        return conclusion_to_standard_calculation(scan, "unreachable")

    if scan.rating == "RESTRICTED":
        return conclusion_to_standard_calculation(scan, "access_restricted")

    if scan.rating == "UNKNOWN":
        return conclusion_to_standard_calculation(scan, "non_http_response")

    if scan.rating == "SOAP":
        return conclusion_to_standard_calculation(scan, "soap")

    if scan.rating == "True":
        return conclusion_to_standard_calculation(scan, "present")
    if scan.rating == "Using CSP":
        return conclusion_to_standard_calculation(scan, "using_csp")
    else:
        if scan.type in ["http_security_header_strict_transport_security"]:

            # special case when no insecure alternatives are offered
            if (
                scan.explanation == "Security Header not present: Strict-Transport-Security, "
                "yet offers no insecure http service."
            ):
                return conclusion_to_standard_calculation(scan, "missing_but_no_insecure_service_offered")

            return conclusion_to_standard_calculation(scan, "missing")

        if scan.type in [
            "http_security_header_x_content_type_options",
            "http_security_header_x_frame_options",
            "http_security_header_x_xss_protection",
        ]:
            return conclusion_to_standard_calculation(scan, "missing")

    # fallback any other conclusion that has not been handled yet, so you can set it ad-hoc
    return conclusion_to_standard_calculation(scan, scan.rating)


def plain_https(scan: Union[EndpointGenericScan, UrlGenericScan]):
    # changed the ratings in the database. They are not really correct.
    # When there is no https at all, it's worse than having broken https. So rate them the same.

    if scan.explanation == "1000":
        return conclusion_to_standard_calculation(scan, "no_https_redirect_and_no_https_on_standard_port")

    # And have redirects looked at: why is there no secure alternative on the standard counterpart port?
    if scan.explanation == "25":
        return conclusion_to_standard_calculation(scan, "https_redirect_on_insecure_port_and_no_https_on_standard_port")

    if scan.explanation == "0":
        return conclusion_to_standard_calculation(scan, "redirecting_properly")

    # fallback any other conclusion that has not been handled yet, so you can set it ad-hoc
    return conclusion_to_standard_calculation(scan, scan.rating)


def dnssec(scan: Union[EndpointGenericScan, UrlGenericScan]):
    return conclusion_to_standard_calculation(scan, scan.rating.lower())


def conclusion_to_standard_calculation(scan: Union[EndpointGenericScan, UrlGenericScan], conclusion: str):
    policy = conclusion_to_score(scan.type, conclusion)
    return apply_policy_to_standard_calculation(scan, policy)


def get_score_from_policy(scan: Union[EndpointGenericScan, UrlGenericScan]):
    policy = conclusion_to_score(scan.type, scan.rating)
    return apply_policy_to_standard_calculation(scan, policy)


def strip_policy_data(policy: ScanPolicy):
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


def apply_policy_to_standard_calculation(scan, policy: ScanPolicy):
    data = strip_policy_data(policy)
    return standard_calculation(scan, **data)


def apply_policy_to_internetnl_calculation(scan, policy: ScanPolicy):
    data = strip_policy_data(policy)
    return standard_calculation_for_internet_nl(scan, **data)


def internet_nl(scan: Union[EndpointGenericScan, UrlGenericScan]):
    # # new internet.nl values for special case. They cannot be aggregated, and are moved into not_applicable
    # # so there are still stats made for them. Perhaps they can be removed as they complicate things?
    # # In the bar charts, group unreachable and untestable (and regular error) into a category test error
    # # (UI and totals row Excel)
    # # not_testable was renamed to untestable in the api 2.0. ["unreachable", "not_testable", "untestable"]:

    # To support old metrics:
    if "~" in scan.rating:
        requirement_level, scan_value = scan.rating.split("~")
        policy = conclusion_to_score(scan.type, scan_value)
        return apply_policy_to_internetnl_calculation(scan, policy)

    # New metrics are a lot simpler, let's hope it stays that way :)
    policy = conclusion_to_score(scan.type, scan.rating)
    return apply_policy_to_internetnl_calculation(scan, policy)


def standard_calculation(
    scan: Union[EndpointGenericScan, UrlGenericScan],
    explanation: str,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    not_testable: bool = False,
    not_applicable: bool = False,
    error_in_test: bool = False,
):

    ok = 0 if any([high, medium, low, not_testable, not_testable, error_in_test]) else 1

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


def standard_calculation_for_internet_nl(
    scan: Union[EndpointGenericScan, UrlGenericScan],
    explanation: str,
    high: int = 0,
    medium: int = 0,
    low: int = 0,
    not_testable: bool = False,
    not_applicable: bool = False,
    error_in_test: bool = False,
):

    # the explanation is a bunch of json, that is not really workable. These fields are split into separate data
    # and should be the same for everything except the score.
    calc = standard_calculation(scan, "", high, medium, low, not_testable, not_applicable, error_in_test)

    # V1 reports do not have json stored in the explanation, only text messages or nothing.
    # So, only parse this is it contains json at all. To improve speed, first check the first letter.
    if explanation[0:1] == "{":
        try:
            data = json.loads(explanation)
            calc["translation"] = data.get("translation", "")
            calc["technical_details"] = scan.evidence
        except json.decoder.JSONDecodeError:
            # not a json value, nothing is done with the explanation field otherwise
            pass

    # The original value contains more nuance than the agregation to high, medium and low. So use the translation but
    # also the original rating to show the correct icon. This is also used to determine the progression compared to
    # the previous scan. This nuance is important as good > good_not_tested.
    calc["test_result"] = scan.rating

    return calc


SCANNER_TO_POLICY_METHOD = {
    "ftp": get_score_from_policy,
    "plain_http": plain_https,
    "dnssec": dnssec,
    "security_headers": http_security_headers,
    "tls_qualys": get_score_from_policy,
    "internet_nl_mail": internet_nl,
    "internet_nl_web": internet_nl,
    "dummy": get_score_from_policy,
}


def get_severity(scan: Union[EndpointGenericScan, UrlGenericScan]) -> Dict[str, Any]:
    scanner = SCAN_TYPES_TO_SCANNER.get(scan.type, {"name": "dummy"})
    calculation = SCANNER_TO_POLICY_METHOD.get(scanner["name"], get_score_from_policy)(scan)

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
