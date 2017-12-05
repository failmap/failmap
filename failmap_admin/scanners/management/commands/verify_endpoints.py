import logging

from django.core.management.base import BaseCommand

import failmap_admin.scanners.scanner_http as scanner_http
from failmap_admin.organizations.models import Organization

from .support.arguments import add_organization_argument

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Verify known endpoints.'

    def add_arguments(self, parser):
        add_organization_argument(parser)

    def handle(self, *args, **options):

        if not options['organization'] or options['organization'][0] == "*":
            scanner_http.verify_endpoints()
        else:
            organization = Organization.objects.all().filter(name=options['organization'][0])
            scanner_http.verify_endpoints(organizations=[organization])
