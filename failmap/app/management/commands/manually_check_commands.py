"""Basic tests to check nothing major is broken."""
from __future__ import absolute_import, unicode_literals

import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """Celery command wrapper."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--clear_entire_database', action='store_true',
                            help='Will remove ALL data from the database.')

        super().add_arguments(parser)

    def handle(self, *args, **options):

        if options['clear_entire_database']:
            run_clean()

        test_all_scanners()


def run_clean():

    # Another protection against idiocy
    from django.conf import settings
    if not settings.DEBUG:
        log.error("Will not clear database in production environment.")
        return

    # requires manual verification
    call_command("clear_database")

    # Load the single organization (Internet Cleanup Foundation)
    log.warning("load_dataset")
    call_command('load_dataset', 'internet_cleanup_foundation')


def test_all_scanners():
    """
    Tests various scanning commands from the command line.

    :param admin_client:
    :return:
    """

    # check the network. No network, you'll fail. Todo: you should be able to reach a domain over the net. Build
    # machines often cannot do this for reasons and things.
    from failmap.scanners.scanner.http import check_network
    log.warning("check_network")
    check_network("real_scanner_test")

    from failmap.organizations.models import Organization, Url
    organization = Organization.objects.filter(name="Internet Cleanup Foundation").get()

    toplevel_urls = Url.objects.all().filter(organization=organization, url__iregex="^[^.]*\.[^.]*$")
    first_toplevel_url = toplevel_urls.first()

    # Run this test here, given the qualys scanner does not rate limit when running standalone.
    # Three urls at the same time will be fine. But if you run this test too often (every few minutes) you'll
    # get errors.
    call_command('scan_tls_qualys', '-v3', '-o', 'Internet Cleanup Foundation')

    from failmap.scanners.scanner.dns import brute_known_subdomains, certificate_transparency, nsec
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
    log.warning("export_organization")
    call_command('export_organization',  'Internet Cleanup Foundation')
    log.warning("rebuild_ratings")
    call_command('rebuild_ratings')
