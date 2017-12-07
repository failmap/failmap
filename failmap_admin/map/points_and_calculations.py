"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import logging

logger = logging.getLogger(__package__)


def points_and_calculation(scan, scan_type):
    if scan_type == "Strict-Transport-Security":
        return security_headers_rating_based_on_scan(scan, scan_type)
    if scan_type == "X-Content-Type-Options":
        return security_headers_rating_based_on_scan(scan, scan_type)
    if scan_type == "X-Frame-Options":
        return security_headers_rating_based_on_scan(scan, scan_type)
    if scan_type == "X-XSS-Protection":
        return security_headers_rating_based_on_scan(scan, scan_type)
    if scan_type == "plain_https":
        return http_plain_rating_based_on_scan(scan)
    if scan_type == "tls_qualys":
        return tls_qualys_rating_based_on_scan(scan)
    return 0, {}


def security_headers_rating_based_on_scan(scan, header='Strict-Transport-Security'):
    security_headers_scores = {
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
        # prevents reflected xss
        'X-XSS-Protection': 100,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
        # prevents clickjacking
        'X-Frame-Options': 200,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options
        # forces the content-type to be leading for defining a type of file (not the browser guess)
        # The browser guess could execute the file, for example with the wrong plugin.
        # Basically the server admin should fix the browser, instead of the other way around.
        'X-Content-Type-Options': 25,

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
        'Strict-Transport-Security': 200,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Public-Key-Pins
        # Has the potential to make your site unreachable if not properly (automatically) maintained
        # The backup cert strategy is also incredibly complex. Creating the right hash is also hard.
        # So if you don't use this. There should be another way to link the content of the site to
        # the transport.
        # header likely to be killed like p3p
        'Public-Key-Pins': 0,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
        # Very complex header to specify what resources can be loaded from where. Especially useful
        # when loading in third party content such as horrible ads. Prevents against xss
        'Content-Security-Policy': 50,

        # Flash, PDF and other exploit prone things can be embedded. Should never happen:
        # the content should always be none(?).
        # if not set to none, it is 200 points for allowing flash and pdf to be embedded at all :)
        'X-Permitted-Cross-Domain-Policies': 25,

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy
        # largely unsupported
        # What referrer should be allowed to access the resource. Security on referrer headers? No.
        'Referrer-Policy': 0
    }

    high = 0
    medium = 0
    low = 0

    # We add what is done well, so it's more obvious it's checked.
    if scan.rating == "True":
        points = 0
        explanation = header + " header present."
    else:
        points = security_headers_scores[scan.type]
        explanation = "Missing " + header + " header."

        if header in ["X-Frame-Options", "Strict-Transport-Security"]:
            medium += 1

        if header in ["Content-Security-Policy", "X-Content-Type-Options", "X-XSS-Protection"]:
            low += 1

    calculation = {
        "type": "security_headers_%s" % header.lower().replace("-", "_"),
        "explanation": explanation,
        "points": points,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }

    return points, calculation


def http_plain_rating_based_on_scan(scan):
    high = 0
    medium = 0

    # scan.rating is "True" or "False", we re-determine the value in this function:
    scan.rating = 0

    # changed the ratings in the database. They are not really correct.
    # When there is no https at all, it's worse than having broken https. So rate them the same.
    if scan.explanation == "Site does not redirect to secure url, and has no secure alternative on a standard port.":
        scan.rating = 1000
        high += 1

    # wrong spelling (history)
    if scan.explanation == "Site does not redirect to secure url, and has nosecure alternative on a standard port.":
        scan.rating = 1000
        high += 1

    # And have redirects looked at: why is there no secure alternative on the standard counterpart port?
    if scan.explanation == "Redirects to a secure site, while a secure counterpart on the standard port is missing.":
        scan.rating = 200
        medium += 1

    # also here: the last scan moment increases with every scan. When you have a set of
    # relevant dates (when scans where made) ....
    calculation = {
        "type": "plain_https",
        "explanation": scan.explanation,
        "points": int(scan.rating),  # generic scans use strings for this field.
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": 0,
    }

    return int(scan.rating), calculation


def tls_qualys_rating_based_on_scan(scan):
    high = 0
    medium = 0
    low = 0

    """
    Qualys gets multiple endpoints
    :param scan: TLSQualysScan
    :return:
    """
    explanations = {
        "F": "Broken Transport Security, rated F",
        "D": "Nearly broken Transport Security, rated D",
        "C": "Less than optimal Transport Security, rated C.",
        "B": "Less than optimal Transport Security, rated B.",
        "A-": "Good Transport Security, rated A-.",
        "A": "Good Transport Security, rated A.",
        "A+": "Perfect Transport Security, rated A+.",
        "T": "Could not establish trust. ",
        "I": "Certificate not valid for domain name.",  # Custom message
        "0": "-",
    }

    # 0? that's port 443 without using TLS. That is extremely rare. In that case...
    # 0 is many cases a "not connect to server" error currently. But there is more.
    # Now checking messages returned from qualys. Certificate invalid for domain name now
    # is awarded points.
    points = {"T": 200,
              "F": 1000,
              "D": 400,
              "I": 200,
              "C": 100,
              "B": 50,
              "A-": 0,
              "A": 0,
              "A+": 0,
              "0": 0}

    # configuration errors, has the rating of 0.
    # Should not happen in new scans anymore. Kept for legacy reasons.
    if scan.qualys_message == "Certificate not valid for domain name":
        scan.qualys_rating = "I"

    if scan.qualys_rating == '0':
        logger.debug("TLS: This tls scan resulted in no https. Not returning a score.")
        return 0, {}

    if scan.qualys_rating == "T":
        gained_points = points[scan.qualys_rating] + points[scan.qualys_rating_no_trust]
        explanation = "%s For the certificate installation: %s" % (
            explanations[scan.qualys_rating], explanations[scan.qualys_rating_no_trust])
    else:
        gained_points = points[scan.qualys_rating]
        explanation = explanations[scan.qualys_rating]

    if scan.qualys_rating in ["T", "F"]:
        high += 1

    if scan.qualys_rating in ["D", "I"]:
        medium += 1

    if scan.qualys_rating in ["B", "C"]:
        low += 1

    rating = {
        "type": "tls_qualys",
        "explanation": explanation,
        "points": gained_points,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }

    return gained_points, rating
