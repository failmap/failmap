import logging

from django.core.management.base import BaseCommand

from failmap.organizations.models import Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Specify an importer and you'll be getting all organizations you'll ever dream of
    """

    def handle(self, *args, **options):

        # make sure there are creation dates etc...
        organizations = Url.objects.all().filter(is_dead=True, is_dead_since__isnull=True)
        for organization in organizations:
            if organization.created_on:
                organization.is_dead_since = organization.created_on
                organization.save()
            else:
                organization.is_dead_since = organization.onboarded_on
                organization.save()

        # missing creation date
        organizations = Url.objects.all().filter(created_on__isnull=True)
        for organization in organizations:
            organization.created_on = organization.onboarded_on
            organization.save()
