from django.core.management.base import BaseCommand

from failmap_admin.map.stats import update_stats


class Command(BaseCommand):
    help = 'Dump all urlrating data in the stats database.'

    def handle(self, *args, **options):
        update_stats()
