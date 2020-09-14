import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):

        organizations = Organization.objects.all()

        for organization in organizations:
            organization.save()

        log.debug("Done!")
