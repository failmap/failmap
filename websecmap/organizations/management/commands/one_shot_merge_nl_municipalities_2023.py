import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.map.logic.openstreetmap import update_coordinates
from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, merge, dissolve
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)

merge_date = datetime(year=2023, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)

opts = {"when": merge_date, "organization_type": "municipality", "country": "NL"}


@transaction.atomic
class Command(BaseCommand):
    help = "Merge Dutch in 2023."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingsverkiezingen_in_Nederland_2022
    def handle(self, *app_labels, **options):
        merge_nl_municipalities_2023()


@transaction.atomic
def merge_nl_municipalities_2023():

    if not Organization.objects.all().filter(name="Voorne aan Zee").exists():
        print("gemeenten Brielle, Hellevoetsluis en Westvoorne: samenvoeging tot een nieuwe gemeente Voorne aan Zee.")
        merge(
            source_organizations_names=["Gemeente Brielle", "Gemeente Hellevoetsluis", "Gemeente Westvoorne"],
            target_organization_name="Gemeente Voorne aan Zee",
            **opts
        )
        add_url_to_new_organization("NL", "municipality", "Voorne aan Zee", "voorneaanzee.nl", merge_date)

    dissolve(
        dissolved_organization_name="Gemeente Weesp",
        target_organization_names=["Gemeente Amsterdam"],
        when=merge_date,
        organization_type="municipality",
        country="NL",
    )

    update_coordinates(countries=["NL"], organization_types=["municipality"], when=merge_date)
