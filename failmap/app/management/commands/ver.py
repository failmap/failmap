import logging

from .... import __version__
from django.core.management.base import BaseCommand
import django
import platform

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Show failmap version"

    def handle(self, *args, **options):

        print("Python version: %s" % platform.python_version())
        print("Django version: %s" % django.get_version())
        print("Failmap version: %s" % __version__)
        print("")
        print("Check for the latest version at: https://gitlab.com/failmap/failmap/")

