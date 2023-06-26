import logging
import platform

import django
from django.core.management.base import BaseCommand

from websecmap import __version__

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Show failmap version"

    def handle(self, *args, **options):
        print(f"Python version: {platform.python_version()}")
        print(f"Django version: {django.get_version()}")
        print(f"Failmap version: {__version__}")
        print("")
        print("Check for the latest version at: https://gitlab.com/failmap/failmap/")
