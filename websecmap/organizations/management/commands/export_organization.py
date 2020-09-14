import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand
from django.core.serializers import serialize

from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__package__)


class Command(DumpDataCommand):
    help = "Create a smaller export for testing."

    FILENAME = "websecmap_organization_export_{}.{options[format]}"

    APP_LABELS = ("organizations", "scanners", "map", "django_celery_beat")

    FORMAT = "json"

    def add_arguments(self, parser):
        parser.add_argument("--organization_names", nargs="*", help="Perform export of these organizations by name.")
        # https://stackoverflow.com/questions/8203622/argparse-store-false-if-unspecified#8203679
        # https://edumaven.com/python-programming/argparse-boolean
        # --all / "all" is used by super.
        super(Command, self).add_arguments(parser)

    def handle(self, *app_labels, **options):

        options["format"] = self.FORMAT

        if options["output"]:
            filename = options["output"]
        else:
            # generate unique filename for every export
            filename = self.FILENAME.format(datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S"), options=options)

        objects = []

        objects += OrganizationType.objects.all()

        regex = "^(" + "|".join(options["organization_names"]) + ")$"
        organizations = list(Organization.objects.all().filter(name__iregex=regex))
        objects += organizations
        objects += Coordinate.objects.all().filter(organization__in=organizations)

        urls = Url.objects.all().filter(organization__in=organizations)
        objects += urls
        objects += UrlGenericScan.objects.all().filter(url__in=urls)

        endpoints = Endpoint.objects.all().filter(url__in=urls)
        objects += endpoints
        objects += EndpointGenericScan.objects.all().filter(endpoint__in=endpoints)

        with open(filename, "w") as f:
            f.write(serialize(self.FORMAT, objects))

        log.info("Wrote %s", filename)
