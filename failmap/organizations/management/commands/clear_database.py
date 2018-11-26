import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.map.models import OrganizationRating, UrlRating
from failmap.organizations.models import Coordinate, Organization, OrganizationType, Promise, Url
from failmap.scanners.models import (Endpoint, EndpointGenericScan, EndpointGenericScanScratchpad,
                                     Screenshot, TlsQualysScratchpad, TlsScan, UrlGenericScan,
                                     UrlIp)

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Deletes map, organization and scanner data from the database.'

    def handle(self, *args, **options):
        askreset()


def askreset():

    # The dev dataset should not mean anything.
    if settings.DEBUG:
        and_its_gone()

    else:
        try:
            print("Do you __REALLY__ want to delete all map, organization and scanner data?")
            answer = input("Type 'YES' if you mean it: ")

            if answer == "YES":
                and_its_gone()
            else:
                nothing_happened()

        except KeyboardInterrupt:
            nothing_happened()


def nothing_happened():
    print("Nothing was deleted.")


def and_its_gone():
    """
    This is not a maintenance friendly way of deleting data.

    There is a thing in django somewhere that determines the order of relationshipts in the model.

    :return:
    """

    # map
    OrganizationRating.objects.all().delete()
    UrlRating.objects.all().delete()

    # scanners
    EndpointGenericScanScratchpad.objects.all().delete()
    UrlGenericScan.objects.all().delete()
    TlsQualysScratchpad.objects.all().delete()
    Screenshot.objects.all().delete()
    EndpointGenericScan.objects.all().delete()
    Endpoint.objects.all().delete()
    UrlIp.objects.all().delete()
    TlsScan.objects.all().delete()

    # organizations
    Promise.objects.all().delete()
    Url.objects.all().delete()
    Coordinate.objects.all().delete()
    Organization.objects.all().delete()
    OrganizationType.objects.all().delete()

    # game
    UrlSubmission.objects.all().delete()
    OrganizationSubmission.objects.all().delete()
    Team.objects.all().delete()
    Contest.objects.all().delete()
