import logging
import os
import sys
from collections import defaultdict

from django.apps import AppConfig
from django.conf import settings

log = logging.getLogger(__name__)


class Websecmap(AppConfig):
    name = 'websecmap.app'
    verbose_name = "Web Security Map"

    def ready(self):
        """Run when Failmap app has fully loaded."""

        # detect if we run inside the autoreloader's second thread
        inner_run = os.environ.get('RUN_MAIN')
        subcommand = sys.argv[1] if len(sys.argv) > 1 else None
        if not inner_run and subcommand and subcommand != 'help':
            # log database settings during init for operational debug purposes
            log.info('Database settings: {ENGINE}, {NAME}, {USER}, {HOST}'.format_map(
                defaultdict(str, **settings.DATABASES['default'])))


default_app_config = 'websecmap.app.Websecmap'
