import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_security_headers import (scan_organization,
                                                             scan_organization_celery)
from failmap_admin.scanners.state_manager import StateManager

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Scan for http sites that don\'t have https'

    def handle(self, *args, **options):
        organizations = StateManager.create_resumed_organizationlist(scanner="Security Headers")
        for organization in organizations:
            StateManager.set_state("Security Headers", organization.name)
            scan_organization_celery(organization)
            return
