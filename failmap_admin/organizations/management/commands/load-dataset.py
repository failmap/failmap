import logging
from datetime import datetime

import pytz
from django.core.management.commands.loaddata import Command as LoadDataCommand
from django.db import connection

from failmap_admin import settings

logger = logging.getLogger(__package__)


# Solves this bug: https://code.djangoproject.com/ticket/18867
class Command(LoadDataCommand):
    help = "Load data, without messages about naive datetimes (bug in pyyaml)"

    def handle(self, *app_labels, **options):

        settings.USE_TZ = False

        super(Command, self).handle(*app_labels, **options)
