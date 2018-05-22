import datetime
import logging

from django.core.management.base import BaseCommand

from failmap.organizations.models import Url
from failmap.scanners.models import Endpoint, EndpointGenericScan, Screenshot, TlsQualysScan

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Everything that can die / is not resolvable etc for a short while is merged in a certain timespan.

    First know that everything in failmap stacks. This is needed to show gaps over time. Consider the following
    timespan:

    January 2017: amsterdam.nl domain exists.
    Februari 2017: amsterdam.nl domain died.
    March 2017: amsterdam.nl domain exists again.

    In order to show this historical data (the outage of amsterdam.nl for a few months), we have an "is_dead" flag on
    each url. When the url is discovered later, a new url is added, with new endpoints and such.

    Due to bad network connections and other unreliable things, it might be that something is declared dead incorrectly.
    For example: something is down a single day and then up again. This might be our fault via coding bugs etc.

    This library helps fixing those issues, mainly to speed up rating rebuilding and debugging.

    This library will merge everything that is dead for a certain timespan (a week) together. So the in the above case
    nothing will hapen. But the following will be merged:

    13 january 2017: my.amsterdam.nl exists
    14 january 2017: my.amsterdam.nl dies
    15 januaru 2017: my.amsterdam.nl exists

    Now there are two "my.amsterdam.nl" urls. This can be the case, but in such a short timespan it just clutters up
    the database with extra records.

    """
    help = 'Merges similar things that have been dead for a very short while.'

    def handle(self, *args, **options):
        merge_endpoints_that_recently_died()


def merge_endpoints_that_recently_died():
    # with a timespan of a week: if within a week a new similar endpoint was created, merge them into the old one.

    # find difference between "is_dead_since" and "discovered_on" for the same url.
    for url in Url.objects.all():

        # merging can only happen with dead endpoints that have similar endpoints within the timespan
        # ordered by oldest first (the "-" syntax is so confusing)
        dead_endpoints = Endpoint.objects.all().filter(url=url, is_dead=True).order_by("is_dead_since")

        for dead_endpoint in dead_endpoints:

            # bugs and manually entering this happen, and then there is still no date. (todo should not be possible)
            if not dead_endpoint.is_dead_since:
                continue

            # similar created within timespan have to be merged. Let's call it an "identical".

            # no scanner takes more than a week
            # dead on january 14. Means that identical endpoints < january 21 are actually the same.
            the_timespan = dead_endpoint.is_dead_since + datetime.timedelta(days=7)

            identical_endpoints = Endpoint.objects.all().filter(
                url=url,
                ip_version=dead_endpoint.ip_version,
                port=dead_endpoint.port,
                protocol=dead_endpoint.protocol,
                discovered_on__gte=dead_endpoint.is_dead_since,  # it's newer
                discovered_on__lte=the_timespan,  # but not too new
            ).order_by("discovered_on")

            if not identical_endpoints:
                continue

            logger.info("Found identical endpoints for %s: " % dead_endpoint)
            logger.info([ep for ep in identical_endpoints])

            for identical_endpoint in identical_endpoints:

                # merge everything that relates to the identical endpoints to the dead_endpoint:
                EndpointGenericScan.objects.all().filter(endpoint=identical_endpoint).update(endpoint=dead_endpoint)
                TlsQualysScan.objects.all().filter(endpoint=identical_endpoint).update(endpoint=dead_endpoint)
                Screenshot.objects.all().filter(endpoint=identical_endpoint).update(endpoint=dead_endpoint)

                # Copy the state of the enpoint. It goes from oldest to newest. So the latest state is used.
                # Only alive endpoints are added, so a big chance that this will be alive.
                dead_endpoint.is_dead = identical_endpoint.is_dead
                dead_endpoint.is_dead_since = identical_endpoint.is_dead_since
                dead_endpoint.is_dead_reason = identical_endpoint.is_dead_reason
                dead_endpoint.save()

                # then remove the identical endpoint, and declare the dead_endpoint to be alive again.
                identical_endpoint.delete()


def remove_short_deaths():
    """
    Remove scans that

    :return:
    """
    raise NotImplementedError
