import datetime
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, Screenshot

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Removes endpoints that died, but a similar endpoint was created within 7 days. Helps recovering from bad network
    connections. The dead endpoint assumes the life-information from the newer endpoint. The newer endpoint is deleted.

    Example:
        Endpoint A 01 jan 2018, amsterdam.nl 80/http IPv4 exists
        Endpoint A 02 jan 2018, amsterdam.nl 80/http IPv4 dies
        Endpoint B 03 jan 2018, amsterdam.nl 80/http IPv4 exists

    After cleaning the outage the following will have happened:

        Endpoint A 01 jan 2018 amsterdam.nl 80/http IPv4 exists
        (endpoint B is deleted, where endpoint A received the "is_dead, is_dead_reason, is_dead_since" fields from B)

    This can save a few hundred endpoints. Especially if your network connection is terrible.

    Command is carried out in a transaction. If an error occurs, the database remains untouched.

    todo: support days parameter.

    """
    help = __doc__

    def handle(self, *args, **options):
        merge_endpoints_that_recently_died()


@transaction.atomic
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

            log.info("Found identical endpoints for %s. (created: %s, died: %s)" % (
                dead_endpoint, dead_endpoint.discovered_on, dead_endpoint.is_dead_since))
            for ep in identical_endpoints:
                log.info("Identical: %s (created: %s, died: %s)" % (ep, ep.discovered_on, ep.is_dead_since))

            for identical_endpoint in identical_endpoints:

                # merge everything that relates to the identical endpoints to the dead_endpoint:
                EndpointGenericScan.objects.all().filter(endpoint=identical_endpoint).update(endpoint=dead_endpoint)
                Screenshot.objects.all().filter(endpoint=identical_endpoint).update(endpoint=dead_endpoint)

                # Copy the state of the enpoint. It goes from oldest to newest. So the latest state is used.
                # Only alive endpoints are added, so a big chance that this will be alive.
                dead_endpoint.is_dead = identical_endpoint.is_dead
                dead_endpoint.is_dead_since = identical_endpoint.is_dead_since
                dead_endpoint.is_dead_reason = identical_endpoint.is_dead_reason
                dead_endpoint.save()

                # then remove the identical endpoint, and declare the dead_endpoint to be alive again.
                identical_endpoint.delete()
