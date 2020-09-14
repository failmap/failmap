import logging

from django.core.management.base import BaseCommand

from websecmap.map.logic.openstreetmap import add_official_websites
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Clear all caches"

    def handle(self, *args, **options):
        organizations_with_wikidata = Organization.objects.all().filter(wikidata__isnull=False)

        for organization_with_wikidata in organizations_with_wikidata:
            add_official_websites(organization_with_wikidata, organization_with_wikidata.wikidata)
