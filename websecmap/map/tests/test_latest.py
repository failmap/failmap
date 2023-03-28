from datetime import timedelta

from django.utils import timezone
from freezegun import freeze_time

from websecmap.map.logic.latest import get_all_latest_scans

from websecmap.organizations.models import Url
from websecmap.scanners.models import EndpointGenericScan, Endpoint


def test_get_all_latest_scans(db, default_scan_metadata, default_policy):

    with freeze_time("2020-01-01 12:00"):
        now = timezone.now()
        yesterday = now - timedelta(days=1)

        # Eg: make a follow up scan with a simple policy:
        # prepare an endpoint:
        u1 = Url.objects.create(url="pki.example.nl")
        e1 = Endpoint.objects.create(url=u1, protocol="http", port="443")

        # Some things that does not match the policy
        EndpointGenericScan.objects.create(
            endpoint=e1,
            rating="F",
            type="tls_qualys_encryption_quality",
            last_scan_moment=now,
            rating_determined_on=yesterday,
        )

        scans = get_all_latest_scans("NL", "municipality")
        assert scans == {
            "remark": "Get the code and all data from our gitlab repo: "
            "https://gitlab.com/internet-cleanup-foundation/",
            "render_date": "2020-01-01T12:00:00+00:00",
            "scans": {},
        }
