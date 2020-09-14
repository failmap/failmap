import logging
import warnings

from django.core.management.commands.loaddata import Command as LoadDataCommand
from django.db import connection

from websecmap import settings

log = logging.getLogger(__package__)


# Solves this bug: https://code.djangoproject.com/ticket/18867
class Command(LoadDataCommand):
    help = "Load data, without messages about naive datetimes (bug in pyyaml)"

    def handle(self, *app_labels, **options):

        # suppressing warnings about naive datetimes:
        # given the USE_TZ feature doesn't work correctly here.
        warnings.filterwarnings(
            "ignore",
            r"DateTimeField .* received a naive datetime",
            RuntimeWarning,
            r"django\.db\.models\.fields",
        )

        # disable foreign key checks, as they currently don't work with create_dataset.
        # and because the exception is garbage: django.db.utils.IntegrityError: FOREIGN KEY constraint failed
        # -> WHAT foreign key constraint, on what line, between what models? We now have nothing and 25 megs of data...
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
            log.debug(
                "Using SQLite database settings, ignoring foreign key checks due to"
                " possible integrity issues on production databases."
            )
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF;")

        # Setting USE_TZ to false during import weirdly DOES NOT suppress the yaml errors.
        settings.USE_TZ = False

        super(Command, self).handle(*app_labels, **options)
