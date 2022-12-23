import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        move_organization_type_to_layer()


def move_organization_type_to_layer():
    organizations = Organization.objects.all()

    for organization in organizations:
        log.debug("Adding layer %s to organization %s", organization.type, organization.name)
        organization.layers.add(organization.type)
