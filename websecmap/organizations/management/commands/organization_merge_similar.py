import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.administration import merge_similar_organizations

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        merge_similar_organizations()
