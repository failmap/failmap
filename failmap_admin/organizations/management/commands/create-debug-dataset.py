import logging

from .create_dataset import Command as CreateDatasetCommand

logger = logging.getLogger(__package__)


class Command(CreateDatasetCommand):
    help = "Create a near complete export for debugging on another server."

    FILENAME = "failmap_debug_dataset_{}.{options[format]}"

    APP_LABELS = ('organizations', 'scanners', 'map', 'django_celery_beat')
