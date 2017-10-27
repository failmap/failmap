import logging
from datetime import datetime

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand

from .datasethelpers import check_referential_integrity

logger = logging.getLogger(__package__)


# Remove ALL organization and URL ratings and rebuild them
class Command(DumpDataCommand):
    help = "Create a near complete export for debugging on another server."

    def handle(self, *app_labels, **options):

        check_referential_integrity()

        filename = "failmap_debug_dataset_%s.yaml" % datetime.now(pytz.utc).strftime("%Y%m%d_%H%M%S")

        # Override default options.
        options["indent"] = 2
        options["format"] = "yaml"
        options["output"] = filename
        options["verbosity"] = 1  # Show progress bar, it's not really helpful though :)

        # Fill the list of things to export
        if not app_labels:
            app_labels = ('organizations', 'scanners', 'map', 'django_celery_beat')

        logger.debug(app_labels)
        logger.debug(options)

        super(Command, self).handle(*app_labels, **options)
