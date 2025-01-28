import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.scanners.scanner.resolve_ip import refresh_ips_from_url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Quicky add all requirements (organization, layer, url, endpoints, etc) to test a certain url with `websecmap scan`.
    """

    def add_arguments(self, parser):
        """Add arguments."""
        parser.add_argument("-u", "--urls", type=str, nargs="+", help="space separated urls")
        super().add_arguments(parser)

    def handle(self, *args, **options):
        layer = OrganizationType(name="devetst")
        layer.save()
        org = Organization(name="devtest")
        org.save()
        org.layers.set([layer])

        for url in options["urls"]:
            url_obj = Url(url=url)
            url_obj.save()
            url_obj.organization.set([org])
            refresh_ips_from_url(url_obj.id)
