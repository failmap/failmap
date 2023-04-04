import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.whois.sidn import update_whois_data

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):

        update_whois_data()
