import logging

from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Url, Organization
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_http import scan_url, scan_urls
from .support.arguments import add_organization_argument

logger = logging.getLogger(__package__)


# todo: add command line arguments: port and protocol.
class Command(BaseCommand):
    help = 'Discover http(s) endpoints on well known ports.'

    def add_arguments(self, parser):
        add_organization_argument(parser)

    def handle(self, *args, **options):

        if not options['organization']:
            discover_endpoints()
            return

        if options['organization'][0] == "_ALL_":
            discover_endpoints()
            return

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
        endpoints = endpoints.filter(endpoint__protocol__in=['http', 'https'])

    if organization:
        endpoints = endpoints.filter(url__organization=organization)

    for endpoint in endpoints:
        scan_url(endpoint.url, endpoint.port, endpoint.protocol)


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

    scan_urls(urls, ports, protocols)
