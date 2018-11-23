import logging

from django.core.management.base import BaseCommand

from failmap.organizations.models import Organization
from failmap.scanners.scanner.dns import (brute_dutch, brute_known_subdomains, brute_three_letters,
                                          certificate_transparency, nsec, search_engines, standard)

from .support.arguments import add_organization_argument

log = logging.getLogger(__package__)


# https://docs.python.org/3/library/argparse.html#required
class Command(BaseCommand):
    example_text = """example:

    failmap scan_dns --organization '*' --scan_type nsec
    failmap scan_dns --organization '*' --scan_type certificate_transparency
        """

    def add_arguments(self, parser):

        add_organization_argument(parser)

        parser.add_argument(
            '--scan_type', '-st',
            nargs='?',
            help="Specify a scan type with --scan_type type. Types available are:",
            choices=['brute_known_subdomains',
                     'brute_three_letters',
                     'brute_dutch',
                     'standard',
                     'search_engines',
                     'certificate_transparency',
                     'nsec'],
            required=True,
            default="brute_known_subdomains"
        )

    def handle(self, *args, **options):
        scan_type = options['scan_type']

        if options['organization']:
            desired_organization = options['organization'][0]
        else:
            desired_organization = "*"

        log.debug("Scan type: %s" % scan_type)
        log.debug("Targetted organization: %s" % desired_organization)

        if '*' in desired_organization:
            for organization in desired_organization:
                self.scan_organization(organization, scan_type)
            return

        else:
            organization = Organization.objects.get(name=desired_organization)
            self.scan_organization(organization, scan_type)

    def scan_organization(self, organization, scan_type):
        log.debug("Calling %s scan on: %s" % (scan_type, organization))

        if scan_type == "brute_three_letters":
            brute_three_letters(organizations=[organization])

        if scan_type == "brute_dutch":
            brute_dutch(organizations=[organization])

        if scan_type == "standard":
            standard(organizations=[organization])

        if scan_type == "search_engines":
            search_engines(organizations=[organization])

        # we don't do anything with added subdomains, that should be handled at the "added url event" or whatever
