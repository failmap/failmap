import argparse
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.state_manager import StateManager
from failmap_admin.scanners.scanner_dns import ScannerDns
from failmap_admin.scanners.scanner_http import ScannerHttp

logger = logging.getLogger(__package__)


# https://docs.python.org/3/library/argparse.html#required
class Command(BaseCommand):
    help = 'Development command'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization', '-o',
            help="Name of an organization, for example Arnhem. Prefix spaces with a backslash (\\)",
            nargs=1,
            required=True,
            type=self.valid_organization
        )

        # options:
        # brute_known_subdomains,
        # brute_three_letters,
        # brute_dutch_basic,
        # standard
        parser.add_argument(
            '--scan_type', '-st',
            nargs='?',
            help="Specify a scan type with --scan_type type. Types available are:",
            choices=['brute_known_subdomains', 'brute_three_letters',
                     'brute_dutch_basic', 'standard', 'search_engines', 'certificate_transparency'],
            required=True,
            default="brute_known_subdomains"
        )

    def handle(self, *args, **options):

        scan_type = options['scan_type']
        desired_organization = options['organization'][0]
        logger.debug("Scan type: %s" % scan_type)
        logger.debug("Desired organization: %s" % desired_organization)

        if '_ALL_' in desired_organization:
            organizations = StateManager.create_resumed_organizationlist(scanner="DNS_" + scan_type)
            for organization in organizations:
                StateManager.set_state("DNS_" + scan_type, organization.name)
                self.scan_organization(organization, scan_type)
            return

        else:
            organization = Organization.objects.get(name=desired_organization)
            self.scan_organization(organization, scan_type)

    @staticmethod
    def valid_organization(name):
        if "_ALL_" in name:
            return "_ALL_"
        try:
            o = Organization.objects.get(name=name)
            return o.name
        except ObjectDoesNotExist:
            msg = "%s is not a valid organization or _ALL_" % name
            raise argparse.ArgumentTypeError(msg)

    def scan_organization(self, organization, scan_type):
        s = ScannerDns()

        scanfunction = ""
        if "brute_known_subdomains" in scan_type:
            scanfunction = "organization_brute_knownsubdomains"
        if "brute_three_letters" in scan_type:
            scanfunction = "organization_brute_threeletters"
        if "brute_dutch_basic" in scan_type:
            scanfunction = "organization_brute_dutch"
        if "standard" in scan_type:
            scanfunction = "organization_standard_scan"
        if "search_engines" in scan_type:
            scanfunction = "organization_search_engines_scan"
        if "certificate_transparency" in scan_type:
            scanfunction = "organization_certificate_transparency"

        logger.debug("Calling %s scan on: %s" % (scanfunction, organization))
        added = getattr(s, scanfunction)(organization)  # dynamically call function
        logger.debug("Added: %s" % added)
        if added:
            logger.debug("Scanning urls on standard ports")
            ScannerHttp.scan_url_list_standard_ports(added)
