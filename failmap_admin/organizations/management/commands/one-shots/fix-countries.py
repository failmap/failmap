import ipaddress
import logging

import tldextract
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Endpoint, TlsQualysScan, Url

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Changes country "netherlands" to "NL"'

    def handle(self, *args, **options):
        countries = Organization.objects.all().filter(country="netherlands")
        for country in countries:
            country.country = "NL"
            country.save()
