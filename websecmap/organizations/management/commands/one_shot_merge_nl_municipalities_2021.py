import logging
from datetime import datetime
from typing import List

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.map.logic.openstreetmap import update_coordinates
from websecmap.map.report import recreate_organization_reports
from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, merge, dissolve
from websecmap.organizations.models import Organization

log = logging.getLogger(__package__)


@transaction.atomic
class Command(BaseCommand):
    help = "Merge Dutch in 2021."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):

        with transaction.atomic():

            # prevent running this twice:
            if Organization.objects.all().filter(name="Eemsdelta").exists():
                raise EnvironmentError("Eemsdelta already exists, this migration was probably run already.")

            merge_date = datetime(year=2021, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)

            """
            De gemeenten Appingedam, Delfzijl en Loppersum: samenvoeging tot een nieuwe gemeente Eemsdelta.[24]
            """
            merge(
                source_organizations_names=["Appingedam", "Delfzijl", "Loppersum"],
                target_organization_name="Eemsdelta",
                when=merge_date,
                organization_type="municipality",
                country="NL",
            )

            """
            Opheffing van de gemeente Haaren en opdeling over de gemeenten Boxtel, Oisterwijk, Vught en Tilburg.[25]
            Biezenmortel wordt bij Tilburg gevoegd, Haaren bij Oisterwijk, Helvoirt bij Vught en Esch bij Boxtel.

            "Haaren bij Oisterwijk" -> It's yours now. They scored very well so that should be easy.
            """
            dissolve(
                dissolved_organization_name="Haaren",
                target_organization_names=["Oisterwijk"],
                when=merge_date,
                organization_type="municipality",
                country="NL",
            )

            # Update the coordinates for all organizations that are now in the database: their shapes will have altered.
            update_coordinates(countries=["NL"], organization_types=["municipality"], when=merge_date)

            # Create new reports that point to these new coordinates.
            rebuild_reports(["Eemsdelta", "Boxtel", "Oisterwijk", "Vucht", "Tilburg"])

            # Add the urls for the new organizations, will be onboarded automatically.
            add_url_to_new_organization("NL", "municipality", "Eemsdelta", "eemsdelta.nl", merge_date)


def rebuild_reports(organizations: List[str]):
    db_organizations = Organization.objects.all().filter(
        name__in=organizations,
        is_dead=False,
        country="NL",
        type__name="municipality",
    )

    recreate_organization_reports([o.pk for o in db_organizations])
