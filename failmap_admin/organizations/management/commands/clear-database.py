import ipaddress
import logging

import tldextract
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.models import OrganizationRating, UrlRating
from failmap_admin.organizations.models import Coordinate, Organization, OrganizationType, Url
from failmap_admin.scanners.models import (Endpoint, EndpointGenericScan,
                                           EndpointGenericScanScratchpad, Screenshot, State,
                                           TlsQualysScan, TlsQualysScratchpad)

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Deletes map, organization and scanner data from the database.'

    def handle(self, *args, **options):
        askreset()


def askreset():
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
    TlsQualysScratchpad.objects.all().delete()
    Screenshot.objects.all().delete()
    State.objects.all().delete()
    EndpointGenericScan.objects.all().delete()
    TlsQualysScan.objects.all().delete()
    Endpoint.objects.all().delete()

    # organizations
    Url.objects.all().delete()
    Coordinate.objects.all().delete()
    Organization.objects.all().delete()
    OrganizationType.objects.all().delete()
