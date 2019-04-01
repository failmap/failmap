import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.map.geojson import update_coordinates
from websecmap.organizations.adminstrative_transformations import add_url_to_new_organization, merge
from websecmap.organizations.models import Organization
from websecmap.reporting.for_map_organizations import recreate_organization_reports

log = logging.getLogger(__package__)


@transaction.atomic
class Command(BaseCommand):
    help = "Starting point for merging organizations"

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        merge_date = datetime(year=2019, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)

        """
        De gemeenten Dongeradeel, Ferwerderadiel en Kollumerland en Nieuwkruisland: samenvoeging tot een
        nieuwe gemeente Noardeast-Fryslân
        """
        merge(
            source_organizations_names=["Dongeradeel", "Ferwerderadiel", "Kollumerland en Nieuwkruisland"],
            target_organization_name="Noardeast-Fryslân",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Geldermalsen, Lingewaal en Neerijnen: samenvoeging tot een nieuwe gemeente West Betuwe.
        """
        merge(
            source_organizations_names=["Geldermalsen", "Lingewaal", "Neerijnen"],
            target_organization_name="West Betuwe",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Groningen, Haren en Ten Boer: samenvoeging tot een nieuwe gemeente Groningen.
        """
        # You don't need to mention the already existing organization.
        merge(
            source_organizations_names=["Haren", "Ten Boer"],
            target_organization_name="Groningen",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Bedum, De Marne, Eemsmond en Winsum (met uitzondering van de dorpen Ezinge, Feerwerd en Garnwerd):
        samenvoeging tot een nieuwe gemeente Het Hogeland.
        """
        merge(
            source_organizations_names=["Bedum", "De Marne", "Eemsmond", "Winsum"],
            target_organization_name="Het Hogeland",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Grootegast, Leek, Marum en Zuidhorn, en de dorpen Ezinge, Feerwerd en Garnwerd van de gemeente
        Winsum: samenvoeging tot een nieuwe gemeente Westerkwartier.
        """
        # Winsum does not need to be named here, as that is purely geographical
        merge(
            source_organizations_names=["Grootegast", "Leek", "Marum", "Zuidhorn"],
            target_organization_name="Westerkwartier",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Nuth, Onderbanken en Schinnen: samenvoeging tot een nieuwe gemeente Beekdaelen.
        """
        merge(
            source_organizations_names=["Nuth", "Onderbanken", "Schinnen"],
            target_organization_name="Beekdaelen",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Aalburg, Werkendam en Woudrichem: samenvoeging tot een nieuwe gemeente Altena.
        """
        merge(
            source_organizations_names=["Aalburg", "Werkendam", "Woudrichem"],
            target_organization_name="Altena",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Haarlemmerliede en Spaarnwoude en Haarlemmermeer: samenvoeging tot een
        nieuwe gemeente Haarlemmermeer
        """
        # You don't need to mention the already existing organization.
        merge(
            source_organizations_names=["Haarlemmerliede en Spaarnwoude"],
            target_organization_name="Haarlemmermeer",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Leerdam, Zederik (provincie Zuid-Holland) en Vianen (provincie Utrecht):
        samenvoeging tot een nieuwe gemeente Vijfheerenlanden. Deze gemeente kwam in de
        provincie Utrecht te liggen.
        """
        merge(
            source_organizations_names=["Leerdam", "Zederik", "Vianen"],
            target_organization_name="Vijfheerenlanden",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Binnenmaas, Cromstrijen, Korendijk, Oud-Beijerland en Strijen:
        samenvoeging tot een nieuwe gemeente Hoeksche Waard.
        """
        merge(
            source_organizations_names=["Binnenmaas", "Cromstrijen", "Korendijk", "Oud-Beijerland", "Strijen"],
            target_organization_name="Hoeksche Waard",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Giessenlanden en Molenwaard: samenvoeging tot een nieuwe gemeente Molenlanden
        """
        merge(
            source_organizations_names=["Giessenlanden", "Molenwaard"],
            target_organization_name="Molenlanden",
            when=merge_date, organization_type="municipality", country="NL"
        )

        """
        De gemeenten Noordwijk en Noordwijkerhout: samenvoeging tot een nieuwe gemeente Noordwijk.
        """
        # You don't need to mention the already existing organization.
        merge(
            source_organizations_names=["Noordwijkerhout"],
            target_organization_name="Noordwijk",
            when=merge_date, organization_type="municipality", country="NL"
        )

        update_coordinates(countries=["NL"], organization_types=["municipality"], when=merge_date)

        organizations = Organization.objects.all().filter(name__in=[
            "Noardeast-Fryslân",
            "West Betuwe",
            "Groningen",
            "Het Hogeland",
            "Westerkwartier",
            "Beekdaelen",
            "Altena",
            "Haarlemmermeer",
            "Vijfheerenlanden",
            "Hoeksche Waard",
            "Molenlanden",
            "Noordwijk"
        ], is_dead=False, country="NL", type__name="municipality")

        recreate_organization_reports(organizations)

        # Add the urls for the new organizations, will be onboarded automatically.
        add_url_to_new_organization("NL", "municipality", "Noardeast-Fryslân", "noardeast-fryslan.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "West Betuwe", "westbetuwe.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Het Hogeland", "hethogeland.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Westerkwartier", "westerkwartier.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Beekdaelen", "beekdaelen.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Altena", "gemeentealtena.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Vijfheerenlanden", "vijfheerenlanden.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Hoeksche Waard", "hoekschewaard.nl", merge_date)
        add_url_to_new_organization("NL", "municipality", "Molenlanden", "molenlanden.nl", merge_date)
