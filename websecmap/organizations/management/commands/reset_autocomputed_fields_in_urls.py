import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Re-calculates autocomputed properties in urls, use to intialize the"

    def handle(self, *args, **options):
        urls = Url.objects.all()
        print("Going to re-calculate and save autocomputed_ values for %s urls." % len(urls))
        [url.save() for url in urls]
        print("Done")
