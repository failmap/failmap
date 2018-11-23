import argparse
import logging
from datetime import datetime
from time import sleep

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from failmap.organizations.models import Url
from failmap.scanners.models import Endpoint

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Can revive endpoints on a certain date. When scans have gone wrong (for example a malfunctioning DNS server or
    network outage), this can restore all killed endpoints (and perhaps later more) on a certain date.

    Without typing --accept, only a preview of the changes will be given.

    This was called undo in the past.

    Examples:

        Preview endpoints to be revived on october 15 2018:
        failmap revive endpoint 2018-10-15

        Revive urls on 15 october 2018:
        failmap revive url 2018-10-15 --accept
    """

    help = __doc__

    subjects = {
        'endpoints': 'endpoints',
        'urls': 'urls',
    }

    def add_arguments(self, parser):
        parser.add_argument('subject', nargs=1, help='The object type you want to revive.', choices=self.subjects)
        parser.add_argument("date", help="The date things went haywire", type=valid_date)
        parser.add_argument("--accept", help="To actually perform this", action='store_false', dest='preview')
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options['subject'][0] not in self.subjects:
                print("Subject cannot be revived, no code for that: %s " % self.subjects.keys())
                return

            revive(options['subject'][0], options['date'], options['preview'])

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}' - The format is YYYY-MM-DD.".format(s)
        raise argparse.ArgumentTypeError(msg)


# This allows for longer / larger revive actions to be cancelled while processing.
@transaction.atomic
def revive(object_type, date, preview: bool = True):
    dead_objects = []

    if object_type == "urls":
        dead_objects = Url.objects.all().filter(is_dead=True, is_dead_since__date=date)

    if object_type == "endpoints":
        dead_objects = Endpoint.objects.all().filter(is_dead=True, is_dead_since__date=date)

    if preview:
        log.info("Previewing the amount of dead %s that will be revived on %s" % (object_type, date))

    log.info("There are %s dead %s this day that will be revived." % (len(dead_objects), object_type))
    log.info("These %s will be revived: %s" % (object_type, dead_objects))

    if preview:
        log.info("No changes where made.")
        return

    log.info("Continuing in 10 seconds, you can still cancel by hitting control+c ...")
    sleep(10)

    for dead_object in dead_objects:
        log.info("Reviving: %s" % dead_object)
        dead_object.is_dead = False
        dead_object.is_dead_since = None
        dead_object.is_dead_reason = "Revived on %s" % datetime.now(pytz.utc)
        dead_object.save(update_fields=['is_dead', 'is_dead_since', 'is_dead_reason'])
