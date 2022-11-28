from websecmap.scanners.scanner.banners.detect_version import (
    SERVICE_IDENTITY_LIKELY_VERSION_FOUND,
    SERVICE_IDENTITY_SOME_IDENTITY_FOUND,
    SERVICE_IDENTITY_NO_BANNER_FOUND,
    detect_a_likely_version,
    remove_ip_addresses,
    remove_ftp_command_numbers,
)


def test_detect_a_likely_version():

    found = SERVICE_IDENTITY_LIKELY_VERSION_FOUND
    maybe = SERVICE_IDENTITY_SOME_IDENTITY_FOUND
    none = SERVICE_IDENTITY_NO_BANNER_FOUND

    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="http") == found
    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="http") == found
    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="http") == found

    assert detect_a_likely_version("Microsoft-IIS/8.5", protocol="http") == maybe
    assert detect_a_likely_version("Micro", protocol="maybe") == maybe

    assert detect_a_likely_version("", protocol="maybe") == none


def test_remove_ip_addresses():
    assert remove_ip_addresses("5717") == "5717"
    assert remove_ip_addresses("txt 13. 46.  12.31.32.5 12.31.32.5 123 567.567") == "txt 13. 46.    123 567.567"
    assert remove_ip_addresses("txt 13. :1 ::1 12:123::3 1:3:1:3:2:1:2:2 a") == "txt 13. :1  3  a"


def test_remove_ftp_command_numbers():
    assert (
        remove_ftp_command_numbers("220 Microsoft FTP Service 234 AUTH command ok. Expecting TLS Negotiation.")
        == " Microsoft FTP Service  AUTH command ok. Expecting TLS Negotiation."
    )
