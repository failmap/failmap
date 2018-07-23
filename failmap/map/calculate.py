"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import logging

log = logging.getLogger(__package__)


def get_calculation(scan):
    # Can be probably more efficient by adding some methods to scan.
    scan_type = getattr(scan, "type", "tls_qualys")
    return calculation_methods[scan_type](scan)


def security_headers_rating_based_on_scan(scan, header='Strict-Transport-Security'):

    # fasing out the header part. You can get this from the scan.
    header = scan.type

    """
    Rationale for classifcation

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
        # prevents reflected xss
        'X-XSS-Protection': 100,
        Classified as: Medium

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
        # prevents clickjacking
        'X-Frame-Options': 200,
        Classified as: High

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options
        # forces the content-type to be leading for defining a type of file (not the browser guess)
        # The browser guess could execute the file, for example with the wrong plugin.
        # Basically the server admin should fix the browser, instead of the other way around.
        'X-Content-Type-Options': 25,
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
        'Strict-Transport-Security': 200,
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
        'Content-Security-Policy': 50,
        Classified as: Low

        # Flash, PDF and other exploit prone things can be embedded. Should never happen:
        # the content should always be none(?).
        # if not set to none, it is 200 points for allowing flash and pdf to be embedded at all :)
        'X-Permitted-Cross-Domain-Policies': 25,
        Classified as: Ignored

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy
        # largely unsupported
        # What referrer should be allowed to access the resource. Security on referrer headers? No.
        'Referrer-Policy':
        Classified as: Ignored
        todo: should be enabled(?)
    """

    high = 0
    medium = 0
    low = 0

    # We add what is done well, so it's more obvious it's checked.
    if scan.rating == "True":
        explanation = header + " header present."

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

        if header in ["Content-Security-Policy", "X-Content-Type-Options", "X-XSS-Protection"]:
            low += 1

    calculation = {
        "type": "security_headers_%s" % header.lower().replace("-", "_"),
        "explanation": explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }

    return calculation


def http_plain_rating_based_on_scan(scan):
    high = 0
    medium = 0

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

    # also here: the last scan moment increases with every scan. When you have a set of
    # relevant dates (when scans where made) ....
    calculation = {
        "type": "plain_https",
        "explanation": scan.explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": 0,
    }

    return calculation


def ftp_rating_based_on_scan(scan):
    # outdated, insecure
    high = 0
    medium = 0
    low = 0

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
    calculation = {
        "type": "ftp",
        "explanation": scan.explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }

    return calculation


def dnssec_rating_based_on_scan(scan):
    """
        See: https://en.wikipedia.org/wiki/Domain_Name_System_Security_Extensions

        In short: DNSSEC quarantees that a domain name matches a certain IP address.
    """

    return {
        "type": "DNSSEC",
        "explanation": scan.explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": 1 if scan.rating == "ERROR" else 0,
        "medium": 0,
        "low": 0,
    }


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

    # configuration errors, has the rating of 0.
    # Should not happen in new scans anymore. Kept for legacy reasons.
    if scan.qualys_message == "Certificate not valid for domain name":
        scan.qualys_rating = "I"

    if scan.qualys_rating == '0':
        log.debug("TLS: This tls scan resulted in no https. Not returning a score.")
        return {}

    if scan.qualys_rating == "T":
        explanation = "%s For the certificate installation: %s" % (
            explanations[scan.qualys_rating], explanations[scan.qualys_rating_no_trust])
    else:
        explanation = explanations[scan.qualys_rating]

    if scan.qualys_rating in ["T", "F"]:
        high += 1

    if scan.qualys_rating in ["D", "I"]:
        medium += 1

    if scan.qualys_rating in ["B", "C"]:
        low += 1

    calculation = {
        "type": "tls_qualys",
        "explanation": explanation,
        "since": scan.rating_determined_on.isoformat(),
        "last_scan": scan.last_scan_moment.isoformat(),
        "high": high,
        "medium": medium,
        "low": low,
    }

    return calculation


# don't re-create the dict every time.
calculation_methods = {
    'Strict-Transport-Security': security_headers_rating_based_on_scan,
    'X-Content-Type-Options': security_headers_rating_based_on_scan,
    'X-Frame-Options': security_headers_rating_based_on_scan,
    'X-XSS-Protection': security_headers_rating_based_on_scan,
    'plain_https': http_plain_rating_based_on_scan,
    'tls_qualys': tls_qualys_rating_based_on_scan,
    'DNSSEC': dnssec_rating_based_on_scan,
    'ftp': ftp_rating_based_on_scan
}
