import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.development_fixture import create_organization_development_fixture

log = logging.getLogger(__package__)


class Command(BaseCommand):
    # You can perform this cycle:
    # websecmap create_development_fixture_organization > testdata_2.json
    # websecmap loaddata testdata_2.json

    # custom organizations:
    # websecmap create_development_fixture_organization 1 2 3 4
    # note: do not use comma's.

    # this is a list of numbers of interesting organizations. Why they are interesting is listed below.
    # these numbers come from the basisbeveiliging database and is used to create a dataset of organizations
    # that contain all kinds of challenges. The goal of this set is to have some realistic development data
    # while not having to load the whole database, which would be ludicrously large for testing purposes.
    default_relevant_organization_ids = [
        # some large municipalities. Close to each other so you can see things like sensible resolution of the
        # polygons on the map. Also see how well organizations perform etc.
        # gemeente amsterdam
        4084,
        # old gemeente amsterdam before a merge, this one is dead
        16,
        # some adjacent municipalities
        # haarlemmermeer, amstelveen, ouder amstel, de ronde venen, stichtste vecht
        3055,
        15,
        257,
        72,
        307,
        # something in the top of NL, Het Hogeland, and something in the south of NL, Vaals
        3051,
        328,
        # an organization that is a dot on this map: vng
        392,
        # some other testing organization the devs have familiarity with
        # Arnhem, Zutphen, Eindhoven
        19,
        385,
        99,
    ]

    def add_arguments(self, parser):
        parser.add_argument("organizations", nargs="*", type=int)
        super().add_arguments(parser)

    def handle(self, *args, **options):
        organizations = options.get("organizations", self.default_relevant_organization_ids)
        # just dump it to stdout so it's easy to copy paste from the shell in production or pipe it to a file.
        print(create_organization_development_fixture(organizations))
