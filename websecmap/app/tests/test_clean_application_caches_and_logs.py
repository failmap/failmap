from datetime import datetime, timezone

from freezegun import freeze_time

from websecmap.app.tasks import clean_application_caches_and_logs
from websecmap.organizations.models import Url
from websecmap.scanners.models import PlannedScan, Scanner


def test_clean_application_caches_and_logs(db):
    clean_application_caches_and_logs()

    url = Url.objects.create(url="test.nl")
    scanner = Scanner.objects.create(name="test")

    with freeze_time("2020-01-01"):
        my_job = PlannedScan()
        my_job.requested_at_when = datetime.now(timezone.utc)
        my_job.url = url
        my_job.scanner = scanner
        my_job.save()

        assert PlannedScan.objects.all().count() == 1
        clean_application_caches_and_logs()
        assert PlannedScan.objects.all().count() == 1

    with freeze_time("2020-01-03"):
        assert PlannedScan.objects.all().count() == 1
        clean_application_caches_and_logs(10)
        assert PlannedScan.objects.all().count() == 1
        clean_application_caches_and_logs(1)
        assert PlannedScan.objects.all().count() == 0
