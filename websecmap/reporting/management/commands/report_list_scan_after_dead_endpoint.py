from django.core.management.base import BaseCommand

from websecmap.scanners.models import Endpoint, EndpointGenericScan


class Command(BaseCommand):
    help = (
        "To debug issue #264: see if there are scans after an endpoint is dead. This results in various"
        "issues where data sticks around and cannot be cleaned up. This can be seen as a bug in reporting,"
        "but as that code is not really clean, try to get a glimpse at the situation first."
    )

    def handle(self, *args, **options):
        list_scans_after_dead_endpoint()


def list_scans_after_dead_endpoint():
    dead_endpoints = Endpoint.objects.all().filter(is_dead=True)
    for dead_endpoint in dead_endpoints:
        scans_after_dead = EndpointGenericScan.objects.all().filter(
            endpoint=dead_endpoint, last_scan_moment__gte=dead_endpoint.is_dead_since
        )
        if scans_after_dead.exists():
            print(f"{dead_endpoint.is_dead_since} Scans after endpoint died: {dead_endpoint}")
            for scan in scans_after_dead:
                print(f" - {scan.last_scan_moment} {scan}")
