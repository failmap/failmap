# Some help to translate the django part.
# This tries to help you avoid remembering the "messages" mess from Django.
import logging
from subprocess import call

from django.core.management.base import BaseCommand

try:
    from pip._internal.utils.misc import get_installed_distributions
except ImportError:  # pip<10
    from pip import get_installed_distributions
    # from pip.utils import get_installed_distributions

logger = logging.getLogger(__package__)


# todo: move to pipenv
class Command(BaseCommand):

    def handle(self, *args, **options):
        packages = [dist.project_name for dist in get_installed_distributions()]
        call("pip install --upgrade " + ' '.join(packages), shell=True)
