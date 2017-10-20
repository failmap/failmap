from __future__ import absolute_import, unicode_literals

import os
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Celery command wrapper."""

    help = __doc__

    def run_from_argv(self, argv):
        """Replace python with celery process with given arguments."""
        appname = __name__.split('.',1)[0] + '.celery:app'
        appname_arguments = ['-A', appname]
        os.execvp(argv[1], argv[1:2] + appname_arguments + argv[2:])
