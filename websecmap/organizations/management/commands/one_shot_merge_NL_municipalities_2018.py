import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.organizations.adminstrative_transformations import dissolve, merge

log = logging.getLogger(__package__)

# geography update needs to have a OSM connection, otherwise it takes too long to process all new coordinates.
# woot.


@transaction.atomic
class Command(BaseCommand):
    help = "Starting point for merging organizations"

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        merge_date = datetime(year=2018, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)

        # testing :)
        # merge(["Assen", "Alkmaar", "Aalten"], "Yolo-Swaggertown", merge_date)
        # merge(["Apeldoorn", "Ameland"], "Dank Memeston", merge_date)
        # merge(["Almere", "Almelo"], "Woot Winston", merge_date)
        # return

        """
        De gemeenten Menaldumadeel, Franekeradeel en Het Bildt zullen opgaan in een nieuwe gemeente Waadhoeke.
        """

        # We use the frysian name: Menameradiel instead of Menaldumadeel
        # we should probably change that here, so the update_coordinates also works. (no, it disappears, so who cares)
        # there is no data of this in OSM etc (afaik).
        merge(
            source_organizations_names=["Menameradiel", "Franekeradeel", "Het Bildt"],
            target_organization_name="Waadhoeke",
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )

        """
        Ook de dorpen Welsrijp, Winsum, Baijum en Spannum van gemeente Littenseradiel,
        sluiten zich bij deze nieuwe gemeente aan.

        Littenseradiel verdwijnt dus. (en waar moeten die heen dan?) De nieuwe gemeenten mogen de erfenis opruimen.
        """
        dissolve(
            dissolved_organization_name="Littenseradiel",
            target_organization_names=["Waadhoeke", "Leeuwarden", "Súdwest-Fryslân"],
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )

        # todo: do a geographic move. This is done via "update_coordinates"
        # todo: add the geographic updates using update_coordinates on a certain date...

        """
        De gemeenteraad van Leeuwarderadeel heeft na een referendum in maart 2013 besloten dat de gemeente zal
        opgaan in de gemeente Leeuwarden.
        """
        merge(
            source_organizations_names=["Leeuwarderadeel"],
            target_organization_name="Leeuwarden",
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )

        """
        Ook zullen tien dorpen van Littenseradiel aan de nieuwe fusiegemeente toegevoegd worden.
        """
        # todo: another geographic move

        """
        De overige vijftien dorpen van Littenseradiel zullen bij de gemeente Súdwest-Fryslân worden gevoegd.
        """
        # todo: another geographic move

        """
        De gemeenten Rijnwaarden en Zevenaar hebben in mei 2016 besloten om te fuseren tot de nieuwe gemeente Zevenaar.
        """
        # straightforward geographic move
        merge(
            source_organizations_names=["Rijnwaarden"],
            target_organization_name="Zevenaar",
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )

        """
        De gemeenten Vlagtwedde en Bellingwedde hebben in oktober 2015 besloten om te fuseren tot de
        nieuwe gemeente Westerwolde.
        """
        # straightforward geographic move
        merge(
            source_organizations_names=["Vlagtwedde", "Bellingwedde"],
            target_organization_name="Westerwolde",
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )

        """
        De gemeenten Hoogezand-Sappemeer, Menterwolde en Slochteren hebben in november 2015 besloten om te fuseren
        tot de nieuwe gemeente Midden-Groningen.
        """

        # straightforward geographic move
        merge(
            source_organizations_names=["Hoogezand-Sappemeer", "Menterwolde", "Slochteren"],
            target_organization_name="Midden-Groningen",
            when=merge_date,
            organization_type="municipality",
            country="NL",
        )
