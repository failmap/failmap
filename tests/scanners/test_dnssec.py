"""Testing parsing of dnssec scanner output."""

from failmap.scanners.scanner.dnssec import analyze_result


def test_analyze_result():

    # standard info
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: INFO Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.212: INFO Nameserver 80.69.67.67 does DNSSEC extra processing.
        3.245: INFO Nameserver 80.69.69.69 does DNSSEC extra processing.
        3.245: INFO Servers for faalkaart.nl have consistent extra processing status.
        3.282: INFO Authenticated denial records found for faalkaart.nl, of type NSEC3.
        3.296: INFO NSEC3PARAM record found for faalkaart.nl.
        3.296: INFO NSEC3 for faalkaart.nl is set to use 100 iterations, which is less than 100 and thus OK.
        3.296: INFO Found DNSKEY record for faalkaart.nl at child.
        3.296: INFO Consistent security for faalkaart.nl.
        3.297: INFO Checking DNSSEC at child (faalkaart.nl)."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "INFO"

    # standard error
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: ERROR Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.348: INFO Algorithm number 7 is OK.
        3.348: INFO Parent DS(faalkaart.nl/7/2/52353) refers to valid key at child: DNSKEY(faalkaart.nl/7/52353)
        3.349: INFO Parent DS(faalkaart.nl) refers to secure entry point (SEP) at child: DS(faalkaart.nl/7/2/52353)
        3.349: INFO DNSSEC parent checks for faalkaart.nl complete.
        3.349: INFO Done testing DNSSEC for faalkaart.nl."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"

    # subtle missing DNSSEC
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: ERROR Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.348: INFO Algorithm number 7 is OK.
        3.348: INFO Parent DS(faalkaart.nl/7/2/52353) refers to valid key at child: DNSKEY(faalkaart.nl/7/52353)
        3.349: INFO Parent DS(faalkaart.nl) refers to secure entry point (SEP) at child: DS(faalkaart.nl/7/2/52353)
        3.349: INFO Did not find DS record something something darkside.
        3.349: INFO Done testing DNSSEC for faalkaart.nl."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"

    # missing translation files
    result = """
    0.000: INFO [DNSSEC:BEGIN] nu.nl
    1.969: INFO [DNSSEC:NO_DS_FOUND] nu.nl
    2.995: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] nu.nl
    3.058: INFO [DNSSEC:NSEC_NOT_FOUND] nu.nl
    3.091: INFO [DNSSEC:DNSKEY_NOT_FOUND] nu.nl
    3.091: INFO [DNSSEC:SKIPPED_NO_KEYS] nu.nl
    3.091: INFO [DNSSEC:END] nu.nl
    """

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"

    # Testing that MISSING_DS warning does not result in a warning, see the scanner documentation that this warning
    # is suppressed.
    result = """
    0.000: INFO [DNSSEC:BEGIN] Vlissingeninbeweging.nl,
    2.333: INFO [DNSSEC:NO_DS_FOUND] Vlissingeninbeweging.nl,
    2.348: INFO [DNSSEC:EXTRA_PROCESSING] 80.69.69.69,
    2.350: INFO [DNSSEC:EXTRA_PROCESSING] 80.69.67.67,
    2.353: INFO [DNSSEC:EXTRA_PROCESSING] 37.97.199.195,
    2.353: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] Vlissingeninbeweging.nl,
    2.356: INFO [DNSSEC:NSEC_FOUND] Vlissingeninbeweging.nl;NSEC3,
    2.357: INFO [DNSSEC:NSEC3PARAM_FOUND] Vlissingeninbeweging.nl,
    2.358: INFO [DNSSEC:NSEC3_ITERATIONS_OK] Vlissingeninbeweging.nl;100;100,
    2.358: INFO [DNSSEC:DNSKEY_FOUND] Vlissingeninbeweging.nl,
    2.358: WARNING [DNSSEC:MISSING_DS] Vlissingeninbeweging.nl,
    2.358: INFO [DNSSEC:CHECKING_CHILD] Vlissingeninbeweging.nl,
    2.358: INFO [DNSSEC:DNSKEY_ALGORITHM] Vlissingeninbeweging.nl;53792;7;RSA-NSEC3-SHA1 ,
    2.358: INFO [DNSSEC:ALGORITHM_OK] 7,
    2.358: INFO [DNSSEC:DNSKEY_ALGORITHM] Vlissingeninbeweging.nl;33720;7;RSA-NSEC3-SHA1 ,
    2.358: INFO [DNSSEC:ALGORITHM_OK] 7,
    2.358: INFO [DNSSEC:DNSKEY_SEP] Vlissingeninbeweging.nl;33720,
    2.358: INFO [DNSSEC:DNSKEY_ALGORITHM] Vlissingeninbeweging.nl;4808;7;RSA-NSEC3-SHA1 ,
    2.358: INFO [DNSSEC:ALGORITHM_OK] 7,
    2.359: INFO [DNSSEC:RRSIG_EXPIRES_AT] Fri Feb 15 23:51:23 2019,
    2.359: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/4808);10540800,
    2.360: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/4808),
    2.360: INFO [DNSSEC:RRSIG_VALID] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/4808),
    2.360: INFO [DNSSEC:RRSIG_EXPIRES_AT] Fri Feb 15 23:51:23 2019,
    2.360: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/33720);10540800,
    2.361: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/33720),
    2.361: INFO [DNSSEC:RRSIG_VALID] RRSIG(Vlissingeninbeweging.nl/IN/DNSKEY/33720),
    2.361: INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] Vlissingeninbeweging.nl,
    2.364: INFO [DNSSEC:RRSIG_EXPIRES_AT] Fri Feb 15 23:51:23 2019,
    2.364: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(Vlissingeninbeweging.nl/IN/SOA/4808);10540800,
    2.364: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(Vlissingeninbeweging.nl/IN/SOA/4808),
    2.364: INFO [DNSSEC:RRSIG_VALID] RRSIG(Vlissingeninbeweging.nl/IN/SOA/4808),
    2.364: INFO [DNSSEC:SOA_VALID_SIGNATURES] Vlissingeninbeweging.nl,
    2.364: INFO [DNSSEC:CHILD_CHECKED] Vlissingeninbeweging.nl,
    2.364: INFO [DNSSEC:END] Vlissingeninbeweging.nl
    """

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "INFO"

    # Verify that other warnings indeed deliver a warning.
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: INFO Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.212: INFO Nameserver 80.69.67.67 does DNSSEC extra processing.
        3.245: INFO Nameserver 80.69.69.69 does DNSSEC extra processing.
        3.245: INFO Servers for faalkaart.nl have consistent extra processing status.
        3.282: INFO Authenticated denial records found for faalkaart.nl, of type NSEC3.
        3.296: INFO NSEC3PARAM record found for faalkaart.nl.
        3.296: WARNING NSEC3 for faalkaart.nl is set to use 100 iterations, which is less than 100 and thus OK.
        3.296: INFO Found DNSKEY record for faalkaart.nl at child.
        3.296: INFO Consistent security for faalkaart.nl.
        3.297: INFO Checking DNSSEC at child (faalkaart.nl)."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "WARNING"
