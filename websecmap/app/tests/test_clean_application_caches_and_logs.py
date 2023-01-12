from datetime import datetime

import pytz
from freezegun import freeze_time

from websecmap.app.models import Job
from websecmap.app.tasks import clean_application_caches_and_logs


def test_clean_application_caches_and_logs(db):
    clean_application_caches_and_logs()

    with freeze_time("2020-01-01"):

        my_job = Job()
        my_job.created_on = datetime.now(pytz.utc)
        my_job.save()

        assert Job.objects.all().count() == 1
        clean_application_caches_and_logs()
        assert Job.objects.all().count() == 1

    with freeze_time("2020-01-03"):
        assert Job.objects.all().count() == 1
        clean_application_caches_and_logs(10)
        assert Job.objects.all().count() == 1
        clean_application_caches_and_logs(1)
        assert Job.objects.all().count() == 0
