"""
Business logic that determines what points and calculations are stored.

This file contains (or should) verbose explantion of why points are given.

"""
import logging
from datetime import datetime

import pytz
from django.conf import settings

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
    if scan.rating == "Unreachable":
        return standard_calculation(scan, "Web server content became unreachable. No HTTP content present.",
                                    high, medium, low)

    if scan.rating == "RESTRICTED":
        return standard_calculation(scan,
                                    "Web server requires authorization to access, headers are not publicly visible.",
                                    high, medium, low)

    if scan.rating == "UNKNOWN":
        return standard_calculation(scan,
                                    "Non HTTP response found, which does not require HTTP security headers.",
                                    high, medium, low)

    if scan.rating == "SOAP":
        return standard_calculation(scan, "Header not relevant for SOAP service.",
                                    high, medium, low)

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


def plain_https(scan):
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


def ftp(scan):
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


def DNSSEC(scan):
    """
        See: https://en.wikipedia.org/wiki/Domain_Name_System_Security_Extensions

        In short: DNSSEC quarantees that a domain name matches a certain IP address.
    """
    high, medium, low = 0, 0, 0

    if scan.rating == "ERROR":
        high += 1

    return standard_calculation(scan, scan.explanation, high, medium, low)


def tls_qualys_certificate_trusted(scan):
    high, medium, low = 0, 0, 0

    explanations = {
        "not trusted": "Certificate is not trusted.",
        "trusted": "Certificate is trusted.",
    }

    explanation = explanations[scan.rating]

    if scan.rating == "not trusted":
        high += 1

    return standard_calculation(scan, explanation, high, medium, low)


def tls_qualys_encryption_quality(scan):
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


def internet_nl_mail_starttls_tls_available(scan):
    if scan.rating == "True":
        return standard_calculation(scan=scan, explanation="STARTTLS Available", high=0, medium=0, low=0)
    elif scan.rating == "mx removed":
        # can we just ignore these types of scans / give no severity etc?
        return standard_calculation(scan=scan, explanation="Not relevant. This address does not receive mail anymore.",
                                    high=0, medium=0, low=0)
    elif scan.rating == "False":
        return standard_calculation(scan=scan, explanation="STARTTLS Missing", high=1, medium=0, low=0)


def internet_nl_mail_auth_spf_exist(scan):
    # https://blog.returnpath.com/how-to-explain-spf-in-plain-english/
    if scan.rating == "True":
        return standard_calculation(scan=scan, explanation="SPF Available", high=0, medium=0, low=0)
    elif scan.rating == "mx removed":
        # can we just ignore these types of scans / give no severity etc?
        return standard_calculation(scan=scan, explanation="Not relevant. This address does not receive mail anymore.",
                                    high=0, medium=0, low=0)
    elif scan.rating == "False":
        return standard_calculation(scan=scan, explanation="SPF Missing", high=0, medium=1, low=0)


def internet_nl_mail_auth_dkim_exist(scan):
    if scan.rating == "True":
        return standard_calculation(scan=scan, explanation="DKIM Available", high=0, medium=0, low=0)
    elif scan.rating == "mx removed":
        # can we just ignore these types of scans / give no severity etc?
        return standard_calculation(scan=scan, explanation="Not relevant. This address does not receive mail anymore.",
                                    high=0, medium=0, low=0)
    elif scan.rating == "False":
        return standard_calculation(scan=scan, explanation="DKIM Missing", high=0, medium=1, low=0)


def internet_nl_mail_auth_dmarc_exist(scan):
    if scan.rating == "True":
        return standard_calculation(scan=scan, explanation="DMARC Available", high=0, medium=0, low=0)
    elif scan.rating == "mx removed":
        # can we just ignore these types of scans / give no severity etc?
        return standard_calculation(scan=scan, explanation="Not relevant. This address does not receive mail anymore.",
                                    high=0, medium=0, low=0)
    elif scan.rating == "False":
        return standard_calculation(scan=scan, explanation="DMARC Missing", high=0, medium=1, low=0)


def internet_nl_generic_boolean_value(scan):
    if scan.rating == "True":
        return standard_calculation(scan=scan, explanation="%s available" % scan.type, high=0, medium=0, low=0)

    # medium and low don't impact percentages. Therefore, categories that are not complete should be treaded as high.
    return standard_calculation(scan=scan, explanation="%s missing" % scan.type, high=1, medium=0, low=0)


def change_internet_nl_severity_to_websecmap_severity(scan, original_requirement_level):
    # Only affected when in settings APPLICATION_NAME = "websecmap", since other apps use
    # other setting files, this would work.
    # how does this code quickly recognize being a standalone websecmap, and not something else.
    # it relies on the APPLICATION_NAME field in settings.py.
    if not hasattr(settings, 'APPLICATION_NAME'):
        return original_requirement_level

    if settings.APPLICATION_NAME != 'websecmap':
        return original_requirement_level

    if scan.type in ['internet_nl_mail_auth_spf_exist', 'internet_nl_mail_auth_dkim_exist',
                     'internet_nl_mail_auth_dmarc_exist']:
        # we see starttls as being the most important mail setting.
        return "recommended"

    return original_requirement_level


def internet_nl_requirement_tilde_value_format(scan):
    """
    See documentation of upgrade_api_response to learn how this parsing works.

    sept 2019:
    Storing the requirement level seems odd. Why wouldn't you just parse that at the moment severity is
    added to the mix? Why is that stored at the moment of scanning? -> This is done because you need the
    entire set of results to determine the severity for internet.nl. Without the entire set, the severity cannot
    be set. Which means the means of retrieving data would be completely different.

    :param scan:
    :return:
    """
    requirement_level, scan_value = scan.rating.split('~')

    requirement_level = change_internet_nl_severity_to_websecmap_severity(scan, requirement_level)

    explanation = f"Test {scan.type} resulted in {scan_value}."
    if len(scan.explanation) > 5:
        explanation += f" Because {scan.explanation}."

    # Just pass the values from sending domain...
    if requirement_level == 'observed_state':
        """
        Observed state is not really a sane representation and it's hard to express in
        graphs. For example: mail_non_sending_domain -> true, what does that mean?
        Is that high, medium, low? Not testable? How is that summed up?
        """
        # feature flags / observed state do not have any value in reporting. They are just
        # artifacts that are shown to the user. This can be any value. (but you do want to make
        # calculations over it... so we should subtract it later from the score / exclude these fields?
        """
        'mail_non_sending_domain' -> true = sum the non-sending domains in a graph. false = sum sending domains...
        a double negation...
        'mail_server_configured'
        'mail_servers_testable'
        'mail_starttls_dane_ta'
        """
        if scan_value == 'passed':
            return standard_calculation(scan=scan, explanation=scan_value, high=0, medium=0, low=0)
        else:
            return standard_calculation(scan=scan, explanation=scan_value, high=1, medium=0, low=0)

    if scan_value == 'passed':
        return standard_calculation(scan=scan, explanation=explanation, high=0, medium=0, low=0)

    if scan_value == 'failed':
        if requirement_level == 'required':
            return standard_calculation(scan=scan, explanation=explanation, high=1, medium=0, low=0)
        if requirement_level == 'recommended':
            return standard_calculation(scan=scan, explanation=explanation, high=0, medium=1, low=0)
        if requirement_level == 'optional':
            return standard_calculation(scan=scan, explanation=explanation, high=0, medium=0, low=1)

    # Not applicable and not testable are fine additions to the set of severity levels we use now.
    # This way scanners can be even more flexible.
    if scan_value == 'not_testable':
        return standard_calculation(scan=scan, explanation=explanation, not_testable=True)

    if scan_value == 'not_applicable':
        return standard_calculation(scan=scan, explanation=explanation, not_applicable=True)

    raise ValueError(f'Cannot determine severity for internet.nl scan type {scan.type}')


def internet_nl_score(scan):
    # Todo: these numbers are completely chosen at random and need to be defined.
    # todo: how to add the score and url to each url in a report? / other special values?
    score = int(scan.rating)

    if score == 100:
        return standard_calculation(scan=scan, explanation=f"{scan.rating} {scan.evidence}", high=0, medium=0, low=0)

    if score > 90:
        return standard_calculation(scan=scan, explanation=f"{scan.rating} {scan.evidence}", high=0, medium=0, low=1)

    if score > 80:
        return standard_calculation(scan=scan, explanation=f"{scan.rating} {scan.evidence}", high=0, medium=0, low=1)

    if score > 70:
        return standard_calculation(scan=scan, explanation=f"{scan.rating} {scan.evidence}", high=0, medium=1, low=0)

    return standard_calculation(scan=scan, explanation=f"{scan.rating} {scan.evidence}", high=1, medium=0, low=0)


def dummy_calculated_values(scan):
    explanation = "This is a dummy scan."
    high, medium, low = 0, 0, 0
    return standard_calculation(scan, explanation, high, medium, low)


def standard_calculation(scan, explanation: str, high: int = 0, medium: int = 0, low: int = 0,
                         not_testable: bool = False, not_applicable: bool = False):

    ok = 0 if high or medium or low or not_testable or not_testable else 1

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
        "not_applicable": not_applicable
    }


# don't re-create the dict every time.
calculation_methods = {
    'http_security_header_strict_transport_security': get_security_header_calculation,
    'http_security_header_x_content_type_options': get_security_header_calculation,
    'http_security_header_x_frame_options': get_security_header_calculation,
    'http_security_header_x_xss_protection': get_security_header_calculation,
    'plain_https': plain_https,
    'DNSSEC': DNSSEC,
    'ftp': ftp,
    'tls_qualys_certificate_trusted': tls_qualys_certificate_trusted,
    'tls_qualys_encryption_quality': tls_qualys_encryption_quality,
    'Dummy': dummy_calculated_values,

    # todo: the new format will change the translation fields of the UI somewhat...
    'internet_nl_mail_starttls_tls_available': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_auth_spf_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_auth_dkim_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_auth_dmarc_exist': internet_nl_requirement_tilde_value_format,

    'internet_nl_mail_ipv6_mx_reach': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_ipv6_ns_reach': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_ipv6_ns_address': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_ipv6_mx_address': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_dnssec_mx_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_dnssec_mx_valid': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_dnssec_mailto_valid': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_dnssec_mailto_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_auth_spf_policy': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_auth_dmarc_policy': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_keyexchange': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_compress': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_cert_sig': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_cert_pubkey': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_dane_rollover': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_secreneg': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_dane_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_dane_valid': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_ciphers': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_clientreneg': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_cert_chain': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_tls_version': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_starttls_cert_domain': internet_nl_requirement_tilde_value_format,

    # categories use the old format
    'internet_nl_mail_dashboard_tls': internet_nl_generic_boolean_value,
    'internet_nl_mail_dashboard_auth': internet_nl_generic_boolean_value,
    'internet_nl_mail_dashboard_dnssec': internet_nl_generic_boolean_value,
    'internet_nl_mail_dashboard_ipv6': internet_nl_generic_boolean_value,
    'internet_nl_mail_dashboard_overall_score': internet_nl_score,

    'internet_nl_mail_legacy_dmarc': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_dkim': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_spf': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_dmarc_policy': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_spf_policy': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_start_tls': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_start_tls_ncsc': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_dnssec_email_domain': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_dnssec_mx': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_dane': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_ipv6_nameserver': internet_nl_requirement_tilde_value_format,
    'internet_nl_mail_legacy_ipv6_mailserver': internet_nl_requirement_tilde_value_format,


    # internet nl web has: 23 views, 1 score, 3 categories, 7 auto generated = 34
    'internet_nl_web_ipv6_ws_similar': internet_nl_requirement_tilde_value_format,

    'internet_nl_web_ipv6_ws_address': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_ipv6_ns_reach': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_ipv6_ws_reach': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_ipv6_ns_address': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_dnssec_valid': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_dnssec_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_keyexchange': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_compress': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_cert_sig': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_cert_pubkey': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_dane_valid': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_secreneg': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_http_hsts': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_http_compress': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_dane_exist': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_http_available': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_ciphers': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_clientreneg': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_tls_version': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_cert_chain': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_http_redirect': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_https_cert_domain': internet_nl_requirement_tilde_value_format,

    # Categories have an old format
    'internet_nl_web_tls': internet_nl_generic_boolean_value,
    'internet_nl_web_dnssec': internet_nl_generic_boolean_value,
    'internet_nl_web_ipv6': internet_nl_generic_boolean_value,
    'internet_nl_web_overall_score': internet_nl_score,

    'internet_nl_web_legacy_dnssec': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_tls_available': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_tls_ncsc_web': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_https_enforced': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_hsts': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_ipv6_nameserver': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_ipv6_webserver': internet_nl_requirement_tilde_value_format,
    'internet_nl_web_legacy_dane': internet_nl_requirement_tilde_value_format,

    # Feature flags are not reported, these are the feature flags that should not be in any report. Only
    # the consequences of these flags will be visible.
    'internet_nl_mail_non_sending_domain': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_mail_server_configured': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_mail_servers_testable': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_mail_starttls_dane_ta': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019

    'internet_nl_mail_auth_dmarc_policy_only': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_mail_auth_dmarc_ext_destination': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_web_appsecpriv': internet_nl_generic_boolean_value,  # Added 24th of May 2019
    'internet_nl_web_appsecpriv_csp': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_web_appsecpriv_referrer_policy': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_web_appsecpriv_x_content_type_options': internet_nl_requirement_tilde_value_format,  # Added 24th of Ma
    'internet_nl_web_appsecpriv_x_frame_options': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
    'internet_nl_web_appsecpriv_x_xss_protection': internet_nl_requirement_tilde_value_format,  # Added 24th of May 2019
}


def get_severity(scan):
    # Can be probably more efficient by adding some methods to scan.
    if not calculation_methods.get(scan.type, None):
        raise ValueError("No calculation available for this scan type: %s" % scan.type)

    calculation = calculation_methods[scan.type](scan)

    if not calculation:
        raise ValueError(f'No calculation available for scan {scan.type}')

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
