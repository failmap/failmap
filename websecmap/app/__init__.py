import logging
import os
import sys
from collections import defaultdict

from django.apps import AppConfig
from django.conf import settings

log = logging.getLogger(__name__)


def force_console_logging():
    debug_log = logging.getLogger("websecmap")
    formatter = logging.Formatter(
        "%(asctime)s\t%(levelname)-8s - %(filename)-20s:%(lineno)-4s - %(funcName)20s() - %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)
    debug_log.addHandler(stream_handler)
    debug_log.setLevel(logging.DEBUG)
    return debug_log


class Websecmap(AppConfig):
    name = "websecmap.app"
    verbose_name = "Web Security Map"

    def ready(self):
        """Run when Failmap app has fully loaded."""

        # detect if we run inside the autoreloader's second thread
        inner_run = os.environ.get("RUN_MAIN")
        subcommand = sys.argv[1] if len(sys.argv) > 1 else None
        if not inner_run and subcommand and subcommand != "help":
            # log database settings during init for operational debug purposes
            for database in settings.DATABASES:
                log.info(
                    "Database settings ({db}): {ENGINE}, {NAME}, {USER}, {HOST}".format_map(
                        defaultdict(str, **settings.DATABASES[database])
                    )
                )


# This statement might be obsoleted by newer versions of the django framework
# RemovedInDjango41Warning: 'websecmap.scanners' defines default_app_config =
# 'websecmap.scanners.apps.ScannersConfig'. Django now detects this configuration automatically.
# You can remove default_app_config.
# default_app_config = "websecmap.app.Websecmap"  # pylint: disable=invalid-name
