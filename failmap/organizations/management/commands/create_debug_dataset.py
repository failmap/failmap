import logging

from failmap.organizations.management.commands.create_dataset import Command as CreateDatasetCommand

log = logging.getLogger(__package__)


class Command(CreateDatasetCommand):
    help = "The debug dataset is the most complete dataset that contains all database data, which results in" \
           "several hundreds or even thousands of megabytes of yaml."

    FILENAME = "failmap_debug_dataset_{}.{options[format]}"

    APP_LABELS = ('organizations', 'scanners', 'map', 'django_celery_beat', 'game', 'hypersh')
