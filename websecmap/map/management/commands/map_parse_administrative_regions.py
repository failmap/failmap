# pylint: disable=C0321, too-many-lines
import logging
import re
from typing import List

from django.core.management.base import BaseCommand
from iso3166 import countries

from websecmap.map.models import AdministrativeRegion
from websecmap.organizations.models import OrganizationType

log = logging.getLogger(__package__)

# Below is a heavily edited list of the OSM administrative region page. It's molded so that spellings of
# near-the-same stuff has the same spelling. It is an approximation of all regions in the world, which constantly
# change. It's possible some things are identified as multiple of the same. It's your choice to see what you
# want to import and show on the map. The supplied list is here for convenience only


class Command(BaseCommand):
    # This is a very quick and dirty script that might skip or break things.
    help = "Downloads Administrative Region from the OSM wiki and imports them into AdministrativeRegion"

    def handle(self, *args, **options):

        with open("osm_wiki_10_column_countries.txt", "r", encoding="utf-8") as file_handle:
            ten_region = file_handle.read()

        with open("osm_wiki_11_column_countries.txt", "r", encoding="utf-8") as file_handle:
            eleven_region = file_handle.read()

        organization_types = dict(OrganizationType.objects.all().values_list("pk", "name", flat=False))
        matches = []

        # the data in this template is slow.
        # first get everything with 10 Region
        both = ten_region + eleven_region
        separate_region_splits = both.split("|-")
        # Undefined variable 'separate_region_split' (undefined-variable)
        for separate_region_split in separate_region_splits:
            region_lines = separate_region_split.split("\n")
            country_code = figure_out_country(region_lines)
            if not country_code:
                continue

            # try to get the organization types we know to the rest of the lines. Do not import the very small
            # Region such as cities, parish and other micro scale stuff as the system cannot handle that yet.
            for counter, line in enumerate(region_lines[2 : len(region_lines)]):
                for organization_type in organization_types.values():
                    # allow matching on different spaces, spellings and longer layer names etc...
                    if "".join(ch for ch in organization_type.lower() if ch.isalnum()) in "".join(
                        ch for ch in line.lower() if ch.isalnum()
                    ):
                        log.debug(
                            "Match, administrative region %s is a %s in %s",
                            counter + 3,
                            organization_type,
                            country_code,
                        )
                        matches.append(
                            {
                                "organization_type": organization_type,
                                "country": country_code,
                                "admin_level": counter + 3,
                            }
                        )
                        continue

        log.info("Found %s matches.", len(matches))

        import_matches(matches)


def import_matches(matches):

    for match in matches:

        otype = OrganizationType.objects.all().filter(name=match["organization_type"]).first()
        if not AdministrativeRegion.objects.all().filter(
            country=match["country"], organization_type=otype, admin_level=match["admin_level"]
        ):

            administrative_region = AdministrativeRegion()
            administrative_region.country = match["country"]
            administrative_region.admin_level = match["admin_level"]
            administrative_region.organization_type = otype
            administrative_region.save()
            log.info("Saved: %s %s = %s", match["country"], match["organization_type"], match["admin_level"])

        else:
            log.info("Exists already: %s %s = %s", match["country"], match["organization_type"], match["admin_level"])


def figure_out_country(lines: List[str]):
    country = re.findall(r"lagicon\|([^}]*)", lines[1], re.MULTILINE)
    if not country:
        # probably a comment line or some sorts
        log.debug("No country found in line %s.", lines[1])
        return None
    log.debug(country[0])
    try:
        isocode = countries.get(country[0])
    except KeyError:
        # handle some fallbacks / mismatches here...
        # mismatches with the 3166 library, as the OSM just does things
        # some countries on the OSM list don't exist anymore... oh well :)

        alternatives = {
            "United Kingdom": "GB",
            "Vietnam": "VN",
            "Bolivia": "BO",
            "United States": "US",
            "Tanzania": "TZ",
            "Syria": "SY",
            "South Korea": "KR",
            "Russia": "RU",
            "the Philippines": "PH",
            "North Korea": "KP",
            "Moldova": "MD",
            "Macedonia": "MK",
            "Iran": "IR",
            "Democratic Republic of the Congo": "CG",
            "Czech Republic": "CZ",
            "the Central African Republic": "CF",
            "Brunei": "BN",
        }

        if country[0] in alternatives:
            return alternatives[country[0]]

        log.error("Country %s was not found.", country[0])
        return None

    return isocode.alpha2
