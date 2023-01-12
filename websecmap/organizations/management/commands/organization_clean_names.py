import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        clean_organization_names()


def clean_organization_names():
    for org in Organization.objects.all():
        cleaned = org.name.strip()
        if cleaned != org.name:
            org.name = cleaned
            org.save()
