import logging
from random import Random

from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_http import scan_url, scan_urls

from .support.arguments import add_discover_verify, add_organization_argument

logger = logging.getLogger(__package__)


# todo: add command line arguments: port and protocol.
class Command(BaseCommand):
    help = 'Discover http(s) endpoints on well known ports.'

    def add_arguments(self, parser):
        add_organization_argument(parser)
        add_discover_verify(parser)  # default verify

    def handle(self, *args, **options):
        # some expansion magic to avoid using eval
        func = "verify_existing_endpoints" if options['method'] == "verify" else "discover_endpoints"
        functionlist = {"verify_existing_endpoints": verify_existing_endpoints,
                        "discover_endpoints": discover_endpoints}

        if not options['organization']:
            functionlist[func]()
            return

        if options['organization'][0] == "_ALL_":
            functionlist[func]()
            return

        organization = Organization.objects.all().filter(name=options['organization'][0])

        functionlist[func](organization=organization)


def verify_existing_endpoints(protocol=None, port=None, organization=None):
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
        # todo: add IP version?
        scan_url(endpoint.protocol, endpoint.url, endpoint.port)


def discover_endpoints(protocol=None, port=None, organization=None):
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

    # scan the urls in a semi-random order
    urls = sorted(urls, key=lambda L: Random().random())

    logger.debug("Going to scan %s urls." % len(urls))

    scan_urls(protocols, urls, ports)
