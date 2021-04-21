import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.models import Endpoint, EndpointGenericScan, Screenshot

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Removes duplicate endpoints.

    Duplicates can be created in case of dns outages. In that case endpoints are set to deleted and
    created afterwards when the dns is restored. In that case, a manual action may lead to "restoring"
    of the database, but in reality a set of queued "new endpoints" will also be created: so both
    the system created endpoints and the administrator made alive endpoints.
    """

    help = __doc__

    def handle(self, *args, **options):
        remove_duplicate_endpoints()


def remove_duplicate_endpoints():
    # oldest first, all endpoints are alive and currently in reports (and thus not useful)
    # done: can this do the same with dead endpoints? no. Because of the stacking pattern.
    eps = Endpoint.objects.all().filter(is_dead=False).order_by("id")

    for endpoint in eps:
        # verify if this endpoint still is in the database, could be removed:
        if not Endpoint.objects.all().filter(id=endpoint.id).first():
            log.debug(f"Not removing duplicates from already removed {endpoint}.")
            continue

        identical_endpoints = get_other_identical_endpoints(endpoint)
        if not identical_endpoints:
            continue

        log.debug(f"Found {len(identical_endpoints)} identical endpoints on {endpoint}.")

        for identical_endpoint in identical_endpoints:
            merge_endpoints(identical=identical_endpoint, target=endpoint)
            identical_endpoint.delete()


def get_other_identical_endpoints(endpoint):
    return (
        Endpoint.objects.all()
        .filter(
            url=endpoint.url,
            protocol=endpoint.protocol,
            port=endpoint.port,
            ip_version=endpoint.ip_version,
            is_dead=False,
        )
        .exclude(pk=endpoint.pk)
    )


def merge_endpoints(identical: Endpoint, target: Endpoint):
    # blindly copy the scans, as only the last scan result will be used anyway. All other
    # things might be noise
    EndpointGenericScan.objects.all().filter(endpoint=identical).update(endpoint=target)
    Screenshot.objects.all().filter(endpoint=identical).update(endpoint=target)
