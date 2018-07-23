import datetime
import logging

import pytz
from django.core.management.base import BaseCommand

from failmap.scanners.models import Endpoint

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Undoes certain things that happened recently. This is a specialists tool that is usually a one-shot.

    It can fix certain issues that where caused by mass-scanning when for example the network died and as a result
    a lot of urls or endpoints died.

    As urls, endpoints and organizations stack over time (being dead etc), soem scanenrs will have already created a
    new endpoint to replace the one that died accidentally. For this you can use the "merge" command, which is also
    a specialists tool that requires reading the manual.

    Usually run this script after merge:
    failmap merge
    failmap undo

    """
    help = 'Merges similar things that have been dead for a very short while.'

    def handle(self, *args, **options):
        # a short warning to help not running this command by accident.
        # in a next commit this command should be empty.
        answer = input("Do you want to undo all endpoint deaths on IPv6/4 in the last 4 days?")
        if answer == "YES":
            http_scanner_undo_endpoint_deaths(in_the_last_n_days=4, ip_version=4)
            http_scanner_undo_endpoint_deaths(in_the_last_n_days=4, ip_version=6)


def http_scanner_undo_endpoint_deaths(in_the_last_n_days: int=1, ip_version: int=6):
    """
    Sets all ipv6 or 4 endpoints to alive that where killed in the past N days.

    Run this if you did a scan for ipv6 networks when no ipv6 network was available.

    :param in_the_last_n_days: number of days between now and the moment a mistake was made
    :param ip_version: 4 or 6
    :return:
    """

    # the endpoint cannot have a "new" endpoint within this timeframe. If so, you should merge.
    dead_endpoints = Endpoint.objects.all().filter(
        is_dead=True,
        is_dead_since__gte=datetime.datetime.now(pytz.utc) - datetime.timedelta(days=in_the_last_n_days),
        ip_version=ip_version,
        is_dead_reason="Not found in HTTP Scanner anymore."
    )

    # can't revive if there is a new endpoint already, those should be merged (as it contains all kinds of related data)
    for dead_endpoint in dead_endpoints:
        has_similar_alive_endpoints = Endpoint.objects.all().filter(
            is_dead=False,  # given only one can be alive at any point.
            ip_version=dead_endpoint.ip_version,
            protocol=dead_endpoint.protocol,
            port=dead_endpoint.port,
            url=dead_endpoint.url
        )
        if not has_similar_alive_endpoints:
            log.info("Undoing death on %s" % dead_endpoint)
            dead_endpoint.is_dead = False
            dead_endpoint.is_dead_reason = ""
            dead_endpoint.is_dead_since = None
            dead_endpoint.save()
        else:
            log.info("Can't undo death on %s as there is a similar alive. Try and merge." % dead_endpoint)
