import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, dissolve, merge
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)

merge_date = datetime(year=2023, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)

opts = {"when": merge_date, "organization_type": "municipality", "country": "NL"}


@transaction.atomic
class Command(BaseCommand):
    help = "Merge Dutch in 2023."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingsverkiezingen_in_Nederland_2022
    def handle(self, *app_labels, **options):
        merge_nl_municipalities_2023()


@transaction.atomic
def merge_nl_municipalities_2023():
    new = "Gemeente Voorne aan Zee"
    if not Organization.objects.all().filter(name=new).exists():
        print("gemeenten Brielle, Hellevoetsluis en Westvoorne: samenvoeging tot een nieuwe gemeente Voorne aan Zee.")
        merge(
            source_organizations_names=["Gemeente Brielle", "Gemeente Hellevoetsluis", "Gemeente Westvoorne"],
            target_organization_name=new,
            **opts,
        )
        add_url_to_new_organization("NL", "municipality", new, "voorneaanzee.nl", merge_date)

    dissolve(
        dissolved_organization_name="Gemeente Weesp",
        target_organization_names=["Gemeente Amsterdam"],
        when=merge_date,
        organization_type="municipality",
        country="NL",
    )
