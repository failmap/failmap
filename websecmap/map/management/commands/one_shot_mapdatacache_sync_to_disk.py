import logging

from django.core.management.base import BaseCommand

from websecmap.map.models import MapDataCache
from websecmap.map.report import sync_model_field_to_disk

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = (
        "MapDataCache used to store all cache as uncompressed json in the database which was expensive. "
        "Now all data is stored as zip files to disk."
    )

    def handle(self, *args, **options):
        sync_model_field_to_disk(model=MapDataCache, json_field="dataset", file_field="dataset_file")
