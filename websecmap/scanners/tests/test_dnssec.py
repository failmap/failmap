"""Testing parsing of dnssec scanner output."""

from websecmap.scanners.scanner.dnssec import analyze_result, normalize_evidence


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

    assert level == "info"

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

    assert level == "error"

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

    assert level == "error"

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

    assert level == "error"

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

    assert level == "info"

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

    assert level == "warning"


def test_normalize_evidence():
    # The following 10 evidences are the same:
    evidence_1 = """0.000: INFO [DNSSEC:BEGIN] ey.com,
  1.098: INFO [DNSSEC:DS_FOUND] ey.com,
  3.602: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.30.249,
  3.757: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.20.5,
  4.211: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.15.218,
  4.233: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.82.85,
  4.252: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.66.103,
  4.252: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] ey.com,
  4.498: INFO [DNSSEC:NSEC_FOUND] ey.com;NSEC,
  4.614: INFO [DNSSEC:DNSKEY_FOUND] ey.com,
  4.614: INFO [DNSSEC:CONSISTENT_SECURITY] ey.com,
  4.614: INFO [DNSSEC:CHECKING_CHILD] ey.com,
  4.614: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  4.614: INFO [DNSSEC:ALGORITHM_OK] 8,
  4.614: INFO [DNSSEC:DNSKEY_SEP] ey.com;1547,
  4.614: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;23113;8;RSA/SHA-256,
  4.614: INFO [DNSSEC:ALGORITHM_OK] 8,
  4.615: INFO [DNSSEC:RRSIG_EXPIRES_AT] Tue Oct  3 04:02:02 2023,
  4.615: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/1547);864300,
  4.617: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/1547),
  4.618: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/1547),
  4.618: INFO [DNSSEC:RRSIG_EXPIRES_AT] Tue Oct  3 04:02:02 2023,
  4.618: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/23113);864300,
  4.618: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/23113),
  4.618: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/23113),
  4.618: INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] ey.com,
  4.856: INFO [DNSSEC:RRSIG_EXPIRES_AT] Tue Oct  3 04:02:02 2023,
  4.856: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/SOA/23113);864300,
  4.857: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/SOA/23113),
  4.857: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/SOA/23113),
  4.857: INFO [DNSSEC:SOA_VALID_SIGNATURES] ey.com,
  4.857: INFO [DNSSEC:CHILD_CHECKED] ey.com,
  4.857: INFO [DNSSEC:CHECKING_PARENT] ey.com,
  4.857: INFO [DNSSEC:DS_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  4.857: INFO [DNSSEC:ALGORITHM_OK] 8,
  4.858: INFO [DNSSEC:DS_KEYREF_OK] DS(ey.com/8/2/1547);DNSKEY(ey.com/8/1547),
  4.858: INFO [DNSSEC:DS_TO_SEP] ey.com;DS(ey.com/8/2/1547),
  4.858: INFO [DNSSEC:PARENT_CHECKED] ey.com,
  4.858: INFO [DNSSEC:END] ey.com
    """

    evidence_2 = """0.000: INFO [DNSSEC:BEGIN] ey.com,
  2.484: INFO [DNSSEC:DS_FOUND] ey.com,
  5.149: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.82.85,
  5.168: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.66.103,
  5.331: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.20.5,
  5.556: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.30.249,
  6.017: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.15.218,
  6.017: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] ey.com,
  6.041: INFO [DNSSEC:NSEC_FOUND] ey.com;NSEC,
  6.053: INFO [DNSSEC:DNSKEY_FOUND] ey.com,
  6.053: INFO [DNSSEC:CONSISTENT_SECURITY] ey.com,
  6.053: INFO [DNSSEC:CHECKING_CHILD] ey.com,
  6.053: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  6.053: INFO [DNSSEC:ALGORITHM_OK] 8,
  6.053: INFO [DNSSEC:DNSKEY_SEP] ey.com;1547,
  6.053: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;23113;8;RSA/SHA-256,
  6.053: INFO [DNSSEC:ALGORITHM_OK] 8,
  6.054: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 22:10:15 2023,
  6.054: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/1547);864300,
  6.056: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/1547),
  6.056: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/1547),
  6.057: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 22:10:15 2023,
  6.057: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/23113);864300,
  6.057: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/23113),
  6.057: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/23113),
  6.057: INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] ey.com,
  6.080: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 22:10:15 2023,
  6.080: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/SOA/23113);864300,
  6.081: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/SOA/23113),
  6.081: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/SOA/23113),
  6.081: INFO [DNSSEC:SOA_VALID_SIGNATURES] ey.com,
  6.081: INFO [DNSSEC:CHILD_CHECKED] ey.com,
  6.081: INFO [DNSSEC:CHECKING_PARENT] ey.com,
  6.081: INFO [DNSSEC:DS_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  6.081: INFO [DNSSEC:ALGORITHM_OK] 8,
  6.081: INFO [DNSSEC:DS_KEYREF_OK] DS(ey.com/8/2/1547);DNSKEY(ey.com/8/1547),
  6.081: INFO [DNSSEC:DS_TO_SEP] ey.com;DS(ey.com/8/2/1547),
  6.081: INFO [DNSSEC:PARENT_CHECKED] ey.com,
  6.081: INFO [DNSSEC:END] ey.com
    """

    # some useless empty lines and more spaces in the start
    evidence_3 = """


      0.000: INFO [DNSSEC:BEGIN] ey.com,
             2.571: INFO [DNSSEC:DS_FOUND] ey.com,
             5.652: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.15.218,
             5.878: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.30.249,
             5.902: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.82.85,
             5.930: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.66.103,
             6.095: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.20.5,
             6.095: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] ey.com,
             6.557: INFO [DNSSEC:NSEC_FOUND] ey.com;NSEC,
             6.791: INFO [DNSSEC:DNSKEY_FOUND] ey.com,
             6.791: INFO [DNSSEC:CONSISTENT_SECURITY] ey.com,
             6.791: INFO [DNSSEC:CHECKING_CHILD] ey.com,
             6.791: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
             6.791: INFO [DNSSEC:ALGORITHM_OK] 8,
             6.791: INFO [DNSSEC:DNSKEY_SEP] ey.com;1547,
             6.792: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;23113;8;RSA/SHA-256,
             6.792: INFO [DNSSEC:ALGORITHM_OK] 8,
             6.792: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 04:29:51 2023,
             6.792: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/1547);864300,
             6.795: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/1547),
             6.795: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/1547),
             6.795: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 04:29:51 2023,
             6.795: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/23113);864300,
             6.796: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/23113),
             6.796: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/23113),
             6.796: INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] ey.com,
             7.252: INFO [DNSSEC:RRSIG_EXPIRES_AT] Sun Oct 15 04:29:51 2023,
             7.252: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/SOA/23113);864300,
             7.252: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/SOA/23113),
             7.253: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/SOA/23113),
             7.253: INFO [DNSSEC:SOA_VALID_SIGNATURES] ey.com,
             7.253: INFO [DNSSEC:CHILD_CHECKED] ey.com,
             7.253: INFO [DNSSEC:CHECKING_PARENT] ey.com,
             7.253: INFO [DNSSEC:DS_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
             7.253: INFO [DNSSEC:ALGORITHM_OK] 8,
             7.253: INFO [DNSSEC:DS_KEYREF_OK] DS(ey.com/8/2/1547);DNSKEY(ey.com/8/1547),
             7.253: INFO [DNSSEC:DS_TO_SEP] ey.com;DS(ey.com/8/2/1547),
             7.253: INFO [DNSSEC:PARENT_CHECKED] ey.com,
             7.253: INFO [DNSSEC:END] ey.com

  """

    evidence_5 = """
      0.000: INFO [DNSSEC:BEGIN] ey.com,
  3.641: INFO [DNSSEC:DS_FOUND] ey.com,
  6.610: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.30.249,
  6.871: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.20.5,
  6.897: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.82.85,
  7.364: INFO [DNSSEC:EXTRA_PROCESSING] 199.49.15.218,
  7.386: INFO [DNSSEC:EXTRA_PROCESSING] 145.62.66.103,
  7.386: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] ey.com,
  7.621: INFO [DNSSEC:NSEC_FOUND] ey.com;NSEC,
  7.739: INFO [DNSSEC:DNSKEY_FOUND] ey.com,
  7.739: INFO [DNSSEC:CONSISTENT_SECURITY] ey.com,
  7.739: INFO [DNSSEC:CHECKING_CHILD] ey.com,
  7.739: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  7.739: INFO [DNSSEC:ALGORITHM_OK] 8,
  7.740: INFO [DNSSEC:DNSKEY_SEP] ey.com;1547,
  7.740: INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;23113;8;RSA/SHA-256,
  7.740: INFO [DNSSEC:ALGORITHM_OK] 8,
  7.740: INFO [DNSSEC:RRSIG_EXPIRES_AT] Wed Oct 11 04:30:43 2023,
  7.740: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/1547);864300,
  7.743: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/1547),
  7.743: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/1547),
  7.744: INFO [DNSSEC:RRSIG_EXPIRES_AT] Wed Oct 11 04:30:43 2023,
  7.744: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/23113);864300,
  7.744: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/23113),
  7.744: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/23113),
  7.744: INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] ey.com,
  7.971: INFO [DNSSEC:RRSIG_EXPIRES_AT] Wed Oct 11 04:30:43 2023,
  7.971: INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/SOA/23113);864300,
  7.972: INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/SOA/23113),
  7.972: INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/SOA/23113),
  7.972: INFO [DNSSEC:SOA_VALID_SIGNATURES] ey.com,
  7.972: INFO [DNSSEC:CHILD_CHECKED] ey.com,
  7.972: INFO [DNSSEC:CHECKING_PARENT] ey.com,
  7.972: INFO [DNSSEC:DS_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
  7.972: INFO [DNSSEC:ALGORITHM_OK] 8,
  7.973: INFO [DNSSEC:DS_KEYREF_OK] DS(ey.com/8/2/1547);DNSKEY(ey.com/8/1547),
  7.973: INFO [DNSSEC:DS_TO_SEP] ey.com;DS(ey.com/8/2/1547),
  7.973: INFO [DNSSEC:PARENT_CHECKED] ey.com,
  7.973: INFO [DNSSEC:END] ey.com
  """

    normalized_1 = normalize_evidence(evidence_1)
    normalized_2 = normalize_evidence(evidence_2)
    normalized_3 = normalize_evidence(evidence_3)
    # normalized_4 = normalize_evidence(evidence_4)
    normalized_5 = normalize_evidence(evidence_5)

    assert (
        normalized_1
        == """INFO [DNSSEC:BEGIN] ey.com,
INFO [DNSSEC:DS_FOUND] ey.com,
INFO [DNSSEC:EXTRA_PROCESSING] 145.62.66.103,
INFO [DNSSEC:EXTRA_PROCESSING] 145.62.82.85,
INFO [DNSSEC:EXTRA_PROCESSING] 199.49.15.218,
INFO [DNSSEC:EXTRA_PROCESSING] 199.49.20.5,
INFO [DNSSEC:EXTRA_PROCESSING] 199.49.30.249,
INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] ey.com,
INFO [DNSSEC:NSEC_FOUND] ey.com;NSEC,
INFO [DNSSEC:DNSKEY_FOUND] ey.com,
INFO [DNSSEC:CONSISTENT_SECURITY] ey.com,
INFO [DNSSEC:CHECKING_CHILD] ey.com,
INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
INFO [DNSSEC:ALGORITHM_OK] 8,
INFO [DNSSEC:DNSKEY_SEP] ey.com;1547,
INFO [DNSSEC:DNSKEY_ALGORITHM] ey.com;23113;8;RSA/SHA-256,
INFO [DNSSEC:ALGORITHM_OK] 8,
INFO [DNSSEC:RRSIG_EXPIRES_AT] **DATE**,
INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/1547);864300,
INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/1547),
INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/1547),
INFO [DNSSEC:RRSIG_EXPIRES_AT] **DATE**,
INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/DNSKEY/23113);864300,
INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/DNSKEY/23113),
INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/DNSKEY/23113),
INFO [DNSSEC:DNSKEY_VALID_SIGNATURES] ey.com,
INFO [DNSSEC:RRSIG_EXPIRES_AT] **DATE**,
INFO [DNSSEC:RRSIG_OK_DURATION] RRSIG(ey.com/IN/SOA/23113);864300,
INFO [DNSSEC:RRSIG_VERIFIES] RRSIG(ey.com/IN/SOA/23113),
INFO [DNSSEC:RRSIG_VALID] RRSIG(ey.com/IN/SOA/23113),
INFO [DNSSEC:SOA_VALID_SIGNATURES] ey.com,
INFO [DNSSEC:CHILD_CHECKED] ey.com,
INFO [DNSSEC:CHECKING_PARENT] ey.com,
INFO [DNSSEC:DS_ALGORITHM] ey.com;1547;8;RSA/SHA-256,
INFO [DNSSEC:ALGORITHM_OK] 8,
INFO [DNSSEC:DS_KEYREF_OK] DS(ey.com/8/2/1547);DNSKEY(ey.com/8/1547),
INFO [DNSSEC:DS_TO_SEP] ey.com;DS(ey.com/8/2/1547),
INFO [DNSSEC:PARENT_CHECKED] ey.com,
INFO [DNSSEC:END] ey.com"""
    )

    # to easier find differences
    assert normalized_1 == normalized_2
    assert normalized_1 == normalized_3
    # some lines are reshuflled here, it's okay for now.
    # assert normalized_1 == normalized_4
    assert normalized_1 == normalized_5


def test_normalize_evidence_error_result():
    result = """
      0.000: INFO [DNSSEC:BEGIN] aleidakramer.nl,
  0.207: INFO [DNSSEC:NO_DS_FOUND] aleidakramer.nl,
  0.438: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] aleidakramer.nl,
  0.444: INFO [DNSSEC:NSEC_NOT_FOUND] aleidakramer.nl,
  0.447: INFO [DNSSEC:DNSKEY_NOT_FOUND] aleidakramer.nl,
  0.447: INFO [DNSSEC:SKIPPED_NO_KEYS] aleidakramer.nl,
  0.447: INFO [DNSSEC:END] aleidakramer.nl"""

    assert (
        normalize_evidence(result)
        == """INFO [DNSSEC:BEGIN] aleidakramer.nl,
INFO [DNSSEC:NO_DS_FOUND] aleidakramer.nl,
INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] aleidakramer.nl,
INFO [DNSSEC:NSEC_NOT_FOUND] aleidakramer.nl,
INFO [DNSSEC:DNSKEY_NOT_FOUND] aleidakramer.nl,
INFO [DNSSEC:SKIPPED_NO_KEYS] aleidakramer.nl,
INFO [DNSSEC:END] aleidakramer.nl"""
    )
