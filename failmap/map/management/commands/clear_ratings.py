import logging

from django.core.management.base import BaseCommand

from failmap.map.models import OrganizationRating, UrlRating

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Deletes ratings from the database. They can be rebuild based on available scanner data.'

    def handle(self, *args, **options):
        askreset()


def askreset():
    try:
        print("Do you __REALLY__ want to delete all ratings?")
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

    There is a thing in django somewhere that determines the order of relationships in the model.

    :return:
    """

    # map
    OrganizationRating.objects.all().delete()
    UrlRating.objects.all().delete()
