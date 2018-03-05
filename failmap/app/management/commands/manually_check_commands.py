"""Basic tests to check nothing major is broken."""

import logging

from django.core.management import call_command

log = logging.getLogger(__package__)


def test_all_scanners():
    """
    Tests various scanning commands from the command line.

    :param admin_client:
    :return:
    """

    # check the network. No network, you'll fail.
    from failmap.scanners.scanner_http import check_network
    log.warning("check_network")
    check_network("real_scanner_test")

    # Load the single organization (Internet Cleanup Foundation)
    log.warning("load_dataset")
    call_command('load_dataset', 'internet_cleanup_foundation')

    from failmap.organizations.models import Organization, Url
    organization = Organization.objects.filter(name="Internet Cleanup Foundation").get()

    toplevel_urls = Url.objects.all().filter(organization=organization, url__iregex="^[^.]*\.[^.]*$")
    first_toplevel_url = toplevel_urls.first()

    from failmap.scanners.scanner_dns import brute_known_subdomains, certificate_transparency, nsec
    log.warning("brute_known_subdomains")
    brute_known_subdomains(urls=[first_toplevel_url])
    log.warning("certificate_transparency")
    certificate_transparency(urls=[first_toplevel_url])
    log.warning("nsec")
    nsec(urls=[first_toplevel_url])

    # for the first three urls, run all possible scans.
    # We're testing that none of below commands crash, regardless of their output.
    # Of course configurations and such can change.
    # how to detect errors? Try except?
    log.warning("scan_dnssec")
    call_command('scan_dnssec', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("discover_endpoints_2")
    call_command('discover_endpoints_2', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("scan_security_headers")
    call_command('scan_security_headers', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("scan_plain_http")
    call_command('scan_plain_http', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("scan_security_headers")
    call_command('scan_security_headers', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("scan_tls_qualys")
    # please slow down -- eentje.
    call_command('scan_tls_qualys', '-v3', '-o', 'Internet Cleanup Foundation')
    log.warning("export_organization")
    call_command('export_organization',  'Internet Cleanup Foundation')
    log.warning("rebuild_ratings")
    call_command('rebuild_ratings')
