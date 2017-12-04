import logging

from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_http import scan_url, scan_urls

from .support.arguments import add_organization_argument

logger = logging.getLogger(__package__)


# todo: add command line arguments: port and protocol.
# Verify that all endpoints we currently have still exist:
# failmap-admin discover-endpoints-http-https --method=verify

# try to find open ports
# failmap-admin discover-endpoints-http-https --method=discover
class Command(BaseCommand):
    help = 'Discover http(s) endpoints on well known ports.'

    def add_arguments(self, parser):
        add_organization_argument(parser)
        return parser.add_argument(
            '--method', '-m',
            help="verify|discover. Verify checks all existing ones, discover tries to find new ones.",
            nargs='?',
            required=False,
            default="verify",
        )

    def handle(self, *args, **options):

        if options['method'] == "verify":

            if not options['organization'] or options['organization'][0] == "*":
                verify_existing_endpoints()
            else:
                organization = Organization.objects.all().filter(name=options['organization'][0])
                verify_existing_endpoints(organization=organization)

        if options['method'] == "discover":

            if not options['organization'] or options['organization'][0] == "*":
                discover_endpoints()
            else:
                organization = Organization.objects.all().filter(name=options['organization'][0])
                discover_endpoints(organization=organization)


def verify_existing_endpoints(port=None, protocol=None, organization=None):
    """
    Checks all http(s) endpoints if they still exist. This is to monitor changes in the existing
    dataset, without contacting an organization too often. It can be checked every few days,
    as trying to find new endpoints is more involved and should not be run more than once every
    two to four weeks.

    The only result this scanner has is the same or less endpoints than we currently have.

    :return: None
    """
    endpoints = Endpoint.objects.all().filter(is_dead=False,
                                              url__not_resolvable=False,
                                              url__is_dead=False)

    if port:
        endpoints = endpoints.filter(port=port)

    if protocol:
        endpoints = endpoints.filter(protocol=protocol)
    else:
        endpoints = endpoints.filter(protocol__in=['http', 'https'])

    if organization:
        endpoints = endpoints.filter(url__organization=organization)

    for endpoint in endpoints:
        scan_url(endpoint.protocol, endpoint.url, endpoint.port)


def discover_endpoints(port=None, protocol=None, organization=None):
    """


    :return: None
    """
    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False).filter()

    if organization:
        urls = urls.filter(organization=organization)

    if protocol:
        protocols = [protocol]
    else:
        protocols = ['http', 'https']

    if port:
        ports = [port]
    else:
        # Yes, HTTP sites on port 443 exist, we've seen many of them. Not just warnings(!).
        # Don't underestimate the flexibility of the internet.
        ports = [80, 81, 82, 88, 443, 8008, 8080, 8088, 8443, 8888, 9443]

    logger.debug("Going to scan %s urls." % urls.count())

    scan_urls(protocols, urls, ports)
