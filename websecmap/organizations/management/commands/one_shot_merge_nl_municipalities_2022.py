import logging
from datetime import datetime
from typing import List

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.map.logic.openstreetmap import update_coordinates
from websecmap.map.report import recreate_organization_reports
from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, merge
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)

merge_date = datetime(year=2021, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)

opts = {"when": merge_date, "organization_type": "municipality", "country": "NL"}


@transaction.atomic
class Command(BaseCommand):
    help = "Merge Dutch in 2021."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        merge_nl_municipalities_2022()


@transaction.atomic
def merge_nl_municipalities_2022():

    if not Organization.objects.all().filter(name="Dijk en Waard").exists():
        print("De gemeenten Heerhugowaard en Langedijk: samenvoeging tot een nieuwe gemeente Dijk en Waard.")
        merge(
            source_organizations_names=["Heerhugowaard", "Langedijk"], target_organization_name="Dijk en Waard", **opts
        )
        add_url_to_new_organization("NL", "municipality", "Dijk en Waard", "dijkenwaard.nl", merge_date)

    if not Organization.objects.all().filter(name="Land van Cuijk").exists():
        print(
            "De gemeenten Boxmeer, Cuijk, Grave, Mill en Sint Hubert en Sint Anthonis: samenvoeging tot een nieuwe "
            "gemeente Land van Cuijk."
        )
        merge(
            source_organizations_names=["Boxmeer", "Cuijk", "Grave", "Mill en Sint Hubert", "Sint Anthonis"],
            target_organization_name="Land van Cuijk",
            **opts
        )
        add_url_to_new_organization("NL", "municipality", "Land van Cuijk", "landvancuijk.nl", merge_date)

    if not Organization.objects.all().filter(name="Maashorst").exists():
        print("De gemeenten Landerd en Uden: samenvoeging tot een nieuwe gemeente Maashorst.[24]")
        merge(source_organizations_names=["Landerd", "Uden"], target_organization_name="Maashorst", **opts)
        add_url_to_new_organization("NL", "municipality", "Maashorst", "gemeentemaashorst.nl", merge_date)

    if Organization.objects.all().filter(name="Beemster", is_dead=False).exists():
        print(
            "De gemeenten Beemster en Purmerend: opheffing van Beemster en toevoeging van het grondgebied aan "
            "Purmerend."
        )
        # Still doing a merge since the OSM source we use does not have the updated tiles.
        # Perhaps we should do a donation.
        # dissolve(dissolved_organization_name="Beemster", target_organization_names=["Purmerend"], **opts)
        merge(source_organizations_names=["Beemster"], target_organization_name="Purmerend", **opts)

    update_coordinates(countries=["NL"], organization_types=["municipality"], when=merge_date)

    """
    Door deze herindelingen nam het aantal gemeenten in Nederland met 7 af tot 345.[noot 2]
    """


def rebuild_reports(organizations: List[str]):
    db_organizations = Organization.objects.all().filter(
        name__in=organizations,
        is_dead=False,
        country="NL",
        type__name="municipality",
    )

    recreate_organization_reports([o.pk for o in db_organizations])
