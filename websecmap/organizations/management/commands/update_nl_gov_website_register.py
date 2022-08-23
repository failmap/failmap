import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.datasources.nl_gov_websiteregister_rijksoverheid import download_and_import

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        download_and_import()
