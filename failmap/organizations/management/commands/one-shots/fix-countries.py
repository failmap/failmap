import logging

from django.core.management.base import BaseCommand

from failmap.organizations.models import Organization

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Changes country "netherlands" to "NL"'

    def handle(self, *args, **options):
        countries = Organization.objects.all().filter(country="netherlands")
        for country in countries:
            country.country = "NL"
            country.save()
