from __future__ import absolute_import, unicode_literals

import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Celery command wrapper."""

    help = __doc__

    # disable (MySQL) check on startup
    # from django 4.2 this needs to be an empty list, instead of just False
    requires_system_checks = []

    def run_from_argv(self, argv):
        """Replace python with celery process with given arguments."""
        appname = __name__.split(".", 1)[0] + ".celery:app"
        appname_arguments = ["-A", appname]
        os.execvp(argv[1], argv[1:2] + appname_arguments + argv[2:])
