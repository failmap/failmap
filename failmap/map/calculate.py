"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import logging
from datetime import datetime

import pytz

log = logging.getLogger(__package__)


def get_security_header_calculation(scan):
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

    high, medium, low = 0, 0, 0

    header = {
        'http_security_header_strict_transport_security': 'Strict-Transport-Security',
        'http_security_header_x_content_type_options': 'X-Content-Type-Options',
        'http_security_header_x_frame_options': 'X-Frame-Options',
        'http_security_header_x_xss_protection': 'X-XSS-Protection',
    }[scan.type]

    # We add what is done well, so it's more obvious it's checked.
    if scan.rating == "True":
        explanation = header + " header present."
    elif scan.rating == "Using CSP":
        explanation = "Content-Security-Policy header found, which covers the security aspect of the %s header." \
                      % header
    else:
        explanation = "Missing " + header + " header."

        if header in ["X-Frame-Options", "Strict-Transport-Security"]:

            # special case when no insecure alternatives are offered
            if scan.explanation == "Security Header not present: Strict-Transport-Security, " \
                                   "yet offers no insecure http service.":
                explanation = "Missing " + header + " header. Offers no insecure alternative service."
                medium += 0
            else:
                medium += 1

        if header in ["X-Content-Type-Options", "X-XSS-Protection"]:
            low += 1

    return standard_calculation(scan, explanation, high, medium, low)


def http_plain_rating_based_on_scan(scan):
    high, medium, low = 0, 0, 0

    # changed the ratings in the database. They are not really correct.
    # When there is no https at all, it's worse than having broken https. So rate them the same.
    if scan.explanation == "Site does not redirect to secure url, and has no secure alternative on a standard port.":
        high += 1

    # wrong spelling (history)
    if scan.explanation == "Site does not redirect to secure url, and has nosecure alternative on a standard port.":
        high += 1

    # And have redirects looked at: why is there no secure alternative on the standard counterpart port?
    if scan.explanation == "Redirects to a secure site, while a secure counterpart on the standard port is missing.":
        medium += 1

    return standard_calculation(scan, scan.explanation, high, medium, low)


def ftp_rating_based_on_scan(scan):
    # outdated, insecure
    high, medium, low = 0, 0, 0

    # changed the ratings in the database. They are not really correct.
    # When there is no https at all, it's worse than having broken https. So rate them the same.
    if scan.rating == "outdated" or scan.rating == "insecure":
        high += 1

    # sometimes we cannot connect, but do see there is an FTP server. As we're not sure, and cannot verify, we'll give
    # this a low rating. It might be wrong. On the other hand: FTP should be implemented properly and doing a FEAT
    # and AUTH TLS should not result in connection resets and such. If that is happening: why is that server public?
    if scan.rating == "unknown":
        medium += 1

    # also here: the last scan moment increases with every scan. When you have a set of
    # relevant dates (when scans where made) ....

    return standard_calculation(scan, scan.explanation, high, medium, low)


def dnssec_rating_based_on_scan(scan):
    """
        See: https://en.wikipedia.org/wiki/Domain_Name_System_Security_Extensions

        In short: DNSSEC quarantees that a domain name matches a certain IP address.
    """
    high, medium, low = 0, 0, 0

    if scan.rating == "ERROR":
        high += 1

    return standard_calculation(scan, scan.explanation, high, medium, low)


def tls_qualys_certificate_trusted_rating_based_on_scan(scan):
    high, medium, low = 0, 0, 0

    explanations = {
        "not trusted": "Certificate is not trusted.",
        "trusted": "Certificate is trusted.",
    }

    explanation = explanations[scan.rating]

    if scan.rating == "not trusted":
        high += 1

    return standard_calculation(scan, explanation, high, medium, low)


def tls_qualys_encryption_quality_rating_based_on_scan(scan):
    high, medium, low = 0, 0, 0

    explanations = {
        "F": "Broken Transport Security, rated F",
        "C": "Less than optimal Transport Security, rated C.",
        "B": "Less than optimal Transport Security, rated B.",
        "A-": "Good Transport Security, rated A-.",
        "A": "Good Transport Security, rated A.",
        "A+": "Perfect Transport Security, rated A+.",
    }

    explanation = explanations[scan.rating]

    if scan.rating in ["F"]:
        high += 1

    if scan.rating in ["B", "C"]:
        low += 1

    return standard_calculation(scan, explanation, high, medium, low)


def dummy_calculated_values(scan):
    explanation = "This is a dummy scan."
    high, medium, low = 0, 0, 0
    return standard_calculation(scan, explanation, high, medium, low)


def standard_calculation(scan, explanation, high, medium, low):
    return {
        "type": scan.type,
        "explanation": explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }


# don't re-create the dict every time.
calculation_methods = {
    'http_security_header_strict_transport_security': get_security_header_calculation,
    'http_security_header_x_content_type_options': get_security_header_calculation,
    'http_security_header_x_frame_options': get_security_header_calculation,
    'http_security_header_x_xss_protection': get_security_header_calculation,
    'plain_https': http_plain_rating_based_on_scan,
    'DNSSEC': dnssec_rating_based_on_scan,
    'ftp': ftp_rating_based_on_scan,
    'tls_qualys_certificate_trusted': tls_qualys_certificate_trusted_rating_based_on_scan,
    'tls_qualys_encryption_quality': tls_qualys_encryption_quality_rating_based_on_scan,
    'Dummy': dummy_calculated_values
}


def get_calculation(scan):
    # Can be probably more efficient by adding some methods to scan.
    if not calculation_methods.get(scan.type, None):
        raise ValueError("No calculation available for this scan type: %s" % scan.type)

    calculation = calculation_methods[scan.type](scan)

    # handle comply or explain
    # only when an explanation is given AND the explanation is still valid when creating the report.
    calculation['is_explained'] = scan.comply_or_explain_is_explained
    calculation['comply_or_explain_explanation'] = scan.comply_or_explain_explanation
    if scan.comply_or_explain_explained_on:
        calculation['comply_or_explain_explained_on'] = scan.comply_or_explain_explained_on.isoformat()
    else:
        calculation['comply_or_explain_explained_on'] = ""

    if scan.comply_or_explain_explanation_valid_until:
        calculation['comply_or_explain_explanation_valid_until'] = \
            scan.comply_or_explain_explanation_valid_until.isoformat()
    else:
        calculation['comply_or_explain_explanation_valid_until'] = ""

    valid = scan.comply_or_explain_is_explained and (
        scan.comply_or_explain_explanation_valid_until > datetime.now(pytz.utc))
    calculation['comply_or_explain_valid_at_time_of_report'] = valid

    # tracking information for the scan (which also might allow upgrading the scan in the future)
    calculation['scan'] = scan.pk
    calculation['scan_type'] = scan.type

    return calculation
