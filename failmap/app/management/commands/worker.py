from __future__ import absolute_import, unicode_literals

import logging
import os

from django_dramatiq.management.commands.rundramatiq import Command as RundramatiqCommand

log = logging.getLogger(__name__)


class Command(RundramatiqCommand):
    """Dramatiq command wrapper."""

    help = __doc__

    # disable (MySQL) check on startup
    requires_system_checks = False

    def add_arguments(self, parser):
        default_broker = os.environ.get("BROKER", 'redis://127.0.0.1:6379/0')
        parser.add_argument('-b', '--broker', default=default_broker, type=str,
                            help='Url to broker.')
        super().add_arguments(parser)

    def discover_tasks_modules(self):
        """Filter non-app modules (like uwsgi) and add dramatiq config."""
        return ['failmap.dramatiq'] + [m for m in super().discover_tasks_modules() if m.startswith(
            'failmap') or m.startswith('django_dramatiq.setup')]

    def handle(self, *args, **kwargs):
        broker = kwargs['broker']
        log.info("Setting broker to: %s", broker)
        os.environ["BROKER"] = broker
        super().handle(*args, **kwargs)
