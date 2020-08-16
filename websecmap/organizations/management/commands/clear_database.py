import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from websecmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from websecmap.map.models import OrganizationReport
from websecmap.organizations.models import Coordinate, Dataset, Organization, OrganizationType, Url
from websecmap.reporting.models import UrlReport
from websecmap.scanners.models import (Endpoint, EndpointGenericScan, EndpointGenericScanScratchpad,
                                       ScanProxy, Screenshot, UrlGenericScan, InternetNLV2Scan, InternetNLV2StateLog)

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
    OrganizationReport.objects.all().delete()
    UrlReport.objects.all().delete()

    # scanners
    InternetNLV2Scan.objects.all().delete()
    InternetNLV2StateLog.objects.all().delete()
    ScanProxy.objects.all().delete()
    UrlGenericScan.objects.all().delete()
    Screenshot.objects.all().delete()
    EndpointGenericScanScratchpad.objects.all().delete()
    EndpointGenericScan.objects.all().delete()
    Endpoint.objects.all().delete()

    # organizations
    Dataset.objects.all().delete()
    Url.objects.all().delete()
    Coordinate.objects.all().delete()
    Organization.objects.all().delete()
    OrganizationType.objects.all().delete()

    # game
    UrlSubmission.objects.all().delete()
    OrganizationSubmission.objects.all().delete()
    Team.objects.all().delete()
    Contest.objects.all().delete()
