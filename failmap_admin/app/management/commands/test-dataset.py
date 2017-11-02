from __future__ import absolute_import, unicode_literals

import warnings

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Verify importing dataset into clean migrated DB."""

    help = __doc__

    def run_from_argv(self, argv):
        """Migrate DB, flush and import dataset."""

        # this command is used to universally verify dataset import into sqlite
        # (development) or mysql (production) databases. Since for sqlite a
        # memory database is used a migration needs to be performed first. For
        # mysql a flush is required to ensure no previous data is present.

        # suppress pyyaml warnings (which doesn't support timezoned datetimes)
        warnings.filterwarnings(
            'ignore', r"DateTimeField .* received a naive datetime",
            RuntimeWarning, r'django\.db\.models\.fields',
        )

        print('+ Running migrations')
        # run migrate quietly as testing/debugging migrations is not priority
        # here.
        call_command('migrate', '-v0')
        print('+ Flusing old data')
        call_command('flush', '--no-input')
        print('+ Importing fixture ' + argv[2])
        call_command('load-dataset', argv[2])
        print('Done')
