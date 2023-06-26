import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, dissolve, merge
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)

merge_date = datetime(year=2021, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

opts = {"when": merge_date, "organization_type": "municipality", "country": "NL"}


@transaction.atomic
class Command(BaseCommand):
    help = "Merge Dutch in 2022."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        merge_nl_municipalities_2022()


@transaction.atomic
def merge_nl_municipalities_2022():
    new = "Gemeente Dijk en Waard"
    if not Organization.objects.all().filter(name=new).exists():
        print("De gemeenten Heerhugowaard en Langedijk: samenvoeging tot een nieuwe gemeente Dijk en Waard.")
        merge(
            source_organizations_names=["Gemeente Heerhugowaard", "Gemeente Langedijk"],
            target_organization_name=new,
            **opts,
        )
        add_url_to_new_organization("NL", "municipality", new, "dijkenwaard.nl", merge_date)

    new = "Gemeente Land van Cuijk"
    if not Organization.objects.all().filter(name=new).exists():
        print(
            "De gemeenten Boxmeer, Cuijk, Grave, Mill en Sint Hubert en Sint Anthonis: samenvoeging tot een nieuwe "
            "gemeente Land van Cuijk."
        )
        merge(
            source_organizations_names=[
                "Gemeente Boxmeer",
                "Gemeente Cuijk",
                "Gemeente Grave",
                "Gemeente Mill en Sint Hubert",
                "Gemeente Sint Anthonis",
            ],
            target_organization_name=new,
            **opts,
        )
        add_url_to_new_organization("NL", "municipality", new, "landvancuijk.nl", merge_date)

    new = "Gemeente Maashorst"
    if not Organization.objects.all().filter(name=new).exists():
        print("De gemeenten Landerd en Uden: samenvoeging tot een nieuwe gemeente Maashorst.[24]")
        merge(source_organizations_names=["Gemeente Landerd", "Gemeente Uden"], target_organization_name=new, **opts)
        add_url_to_new_organization("NL", "municipality", new, "gemeentemaashorst.nl", merge_date)

    if Organization.objects.all().filter(name="Gemeente Beemster", is_dead=False).exists():
        print(
            "De gemeenten Beemster en Purmerend: opheffing van Beemster en toevoeging van het grondgebied aan "
            "Purmerend."
        )
        # Still doing a merge since the OSM source we use does not have the updated tiles.
        # Perhaps we should do a donation.
        dissolve(
            dissolved_organization_name="Gemeente Beemster", target_organization_names=["Gemeente Purmerend"], **opts
        )
        # merge(source_organizations_names=["Gemeente Beemster"], target_organization_name="Gemeente Purmerend", **opts)

    """
    Door deze herindelingen nam het aantal gemeenten in Nederland met 7 af tot 345.[noot 2]
    """
