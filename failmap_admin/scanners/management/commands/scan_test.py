from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.scanner_dns import ScannerDns
from failmap_admin.scanners.scanner_http import ScannerHttp


class Command(BaseCommand):
    help = 'Development command'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization',
            nargs=1
        )

    def handle(self, *args, **options):
        # todo, move to organization. And how do we know what URL is "top level". Or that
        # at one point there will be organizations wiht the same name in different branches.
        # it's not a "generic" url. This needs to be recorded somewhere. - now we check for 1 dot in
        # the domain name.
        if options['organization']:
            s = ScannerDns()

            if options['organization'][0] == '_ALL_':
                # todo: some domains always return a positive dnsrecon.
                organizations = StateManager.create_resumed_organizationlist(
                    scanner="DNS_knownsubdomains")
                for organization in organizations:
                    StateManager.set_state("DNS_knownsubdomains", organization.name)
                    # todo: this could happen in parallel.
                    added = s.organization_brute_knownsubdomains(organization)
                    ScannerHttp.scan_url_list_standard_ports(added)
            else:
                print("Looking for organization: %s" % options['organization'][0])
                try:
                    o = Organization.objects.get(name=options['organization'][0])
                    # s.dnsrecon_brute_threeletters(o)
                    added = s.organization_brute_knownsubdomains(o)
                    ScannerHttp.scan_url_list_standard_ports(added)
                except ObjectDoesNotExist:
                    print("Organization was not found.")
