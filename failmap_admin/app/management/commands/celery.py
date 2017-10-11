from __future__ import absolute_import, unicode_literals

import os
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Celery command wrapper."""

    help = __doc__

    def run_from_argv(self, argv):
        """Replace python with celery process with given arguments."""
        os.execvp(argv[1], argv[1:])
