import logging

from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.scanner_dns import (brute_dutch, brute_known_subdomains,
                                                brute_three_letters, certificate_transparency, nsec,
                                                search_engines, standard)
from failmap_admin.scanners.state_manager import StateManager

from .support.arguments import add_organization_argument

logger = logging.getLogger(__package__)


# https://docs.python.org/3/library/argparse.html#required
class Command(BaseCommand):
    example_text = """example:

    failmap-admin scan_dns --organization '*' --scan_type nsec
    failmap-admin scan_dns --organization '*' --scan_type certificate_transparency
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
        desired_organization = options['organization'][0]
        logger.debug("Scan type: %s" % scan_type)
        logger.debug("Targetted organization: %s" % desired_organization)

        if '*' in desired_organization:
            organizations = StateManager.create_resumed_organizationlist(scanner="DNS_" + scan_type)
            for organization in organizations:
                StateManager.set_state("DNS_" + scan_type, organization.name)
                self.scan_organization(organization, scan_type)
            return

        else:
            organization = Organization.objects.get(name=desired_organization)
            self.scan_organization(organization, scan_type)

    def scan_organization(self, organization, scan_type):
        logger.debug("Calling %s scan on: %s" % (scan_type, organization))

        # explicitly written so the imported functions are used, don't use strings as dynamic function names.
        if scan_type == "brute_known_subdomains":
            brute_known_subdomains(organizations=[organization])

        if scan_type == "brute_three_letters":
            brute_three_letters(organizations=[organization])

        if scan_type == "brute_dutch":
            brute_dutch(organizations=[organization])

        if scan_type == "standard":
            standard(organizations=[organization])

        if scan_type == "search_engines":
            search_engines(organizations=[organization])

        if scan_type == "certificate_transparency":
            certificate_transparency(organizations=[organization])

        if scan_type == "nsec":
            nsec(organizations=[organization])

        # we don't do anything with added subdomains, that should be handled at the "added url event" or whatever
