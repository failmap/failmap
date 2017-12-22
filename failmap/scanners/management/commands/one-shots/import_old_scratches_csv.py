import logging

from django.core.management.base import BaseCommand

from failmap.scanners.models import TlsQualysScratchpad

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Imports some old scratches for debugging'

    """
    You probably don't need to run this anymore...

    Non resolvable, alsways 0 scans are just nonsense: the domain just doesn't exist and it creates
    false scores.
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        import csv

        # Open our data file in read-mode.
        csvfile = open('old_scratches.csv', 'r')

        # Save a CSV Reader object.
        datareader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row_index, row in enumerate(datareader):
            if row_index == 0:
                continue

            s = TlsQualysScratchpad()
            s.domain = row[0]
            s.when = row[1]
            s.data = row[2]
            # s.save()
