import json

import pytest

from websecmap.scanners.scanner.banners.detect_version import (
    SERVICE_IDENTITY_LIKELY_VERSION_FOUND,
    SERVICE_IDENTITY_NO_BANNER_FOUND,
    SERVICE_IDENTITY_SOME_IDENTITY_FOUND,
    add_excepted_banner_to_config,
    clean_banner,
    contains_version_number,
    detect_a_likely_version,
    remove_ftp_command_numbers,
    remove_ip_addresses,
)


@pytest.mark.override_config(BANNERGRAB_GENERIC_BANNERS='["Something Version 1.2.3"]')
def test_detect_a_likely_version(db):

    found = SERVICE_IDENTITY_LIKELY_VERSION_FOUND
    maybe = SERVICE_IDENTITY_SOME_IDENTITY_FOUND
    none = SERVICE_IDENTITY_NO_BANNER_FOUND

    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="ssh") == found
    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="ssh") == found
    assert detect_a_likely_version("SSH-2.0-OpenSSH_7.6p1 Ubuntu-4ubuntu0.5", protocol="ssh") == found

    assert detect_a_likely_version("Microsoft-IIS/8.5", protocol="http") == maybe
    assert detect_a_likely_version("Micro", protocol="maybe") == maybe

    assert detect_a_likely_version("", protocol="maybe") == none

    assert (
        detect_a_likely_version(
            "HTTP/1.0 408 Request Time-out\x0D\x0ACache-Control: no-cachex0AConnection: "
            "close\x0D\x0AContent-Type: text/html\x0D\x0A\x0D\x0A<h tml><body><h1>408 "
            "Request Time-out</h1>\x0AYour browser didn't send a c omplete request in time."
            "\x0A</body></html>",
            protocol="http",
        )
        == none
    )

    assert detect_a_likely_version("Something something 2.3", protocol="http") == found

    assert detect_a_likely_version("Something something 2.3.4", protocol="http") == found

    assert detect_a_likely_version("Something something version 2", protocol="http") == found

    # excepted via the admin
    assert detect_a_likely_version("Something Version 1.2.3", protocol="http") == found


def test_contains_version_number():
    assert contains_version_number("abc 1.2 asd") is True
    assert contains_version_number("1.2") is True
    assert contains_version_number("abc 1.2.3 asd") is True
    assert contains_version_number("1.2.3") is True
    assert contains_version_number("abc 1 asd") is False
    assert contains_version_number("") is False


def test_remove_ip_addresses():
    assert remove_ip_addresses("5717") == "5717"
    assert remove_ip_addresses("txt 13. 46.  12.31.32.5 12.31.32.5 123 567.567") == "txt 13. 46.    123 567.567"
    assert remove_ip_addresses("txt 13. :1 ::1 12:123::3 1:3:1:3:2:1:2:2 a") == "txt 13. :1  3  a"


def test_remove_ftp_command_numbers():
    assert (
        remove_ftp_command_numbers("220 Microsoft FTP Service 234 AUTH command ok. Expecting TLS Negotiation.")
        == " Microsoft FTP Service  AUTH command ok. Expecting TLS Negotiation."
    )


def test_clean_banner():
    assert clean_banner("SSH-2.0-OpenSSH_7.6p1", "ssh") == "ssh-2.0-openssh_7.6p1"
    assert clean_banner("Apache", "http") == "apache"
    assert clean_banner("Apache", "https") == "apache"
    assert clean_banner("Apache", "tcpwrapped") == "apache"
    assert clean_banner("Apache 196.168.2.2", "tcpwrapped") == "apache"
    assert clean_banner("http/1.0 408 request time-out\x0d\x0acache-control: no-cache", "http") == ""
    assert clean_banner("ssh-2.0-mod_sftp\x0d\x0a\x00\x00\x01\x94\x04\x14\x1c\x9e`\xaew", "http") == ""


def test_add_excepted_banner_to_config(db):
    from constance import config

    assert config.BANNERGRAB_GENERIC_BANNERS == '["apache", "nginx"]'

    add_excepted_banner_to_config("test")
    assert sorted(json.loads(config.BANNERGRAB_GENERIC_BANNERS)) == sorted(["apache", "nginx", "test"])

    add_excepted_banner_to_config("belgie")
    assert sorted(json.loads(config.BANNERGRAB_GENERIC_BANNERS)) == sorted(["apache", "nginx", "test", "belgie"])

    add_excepted_banner_to_config("brussel")

    assert sorted(json.loads(config.BANNERGRAB_GENERIC_BANNERS)) == sorted(
        ["apache", "nginx", "test", "belgie", "brussel"]
    )
