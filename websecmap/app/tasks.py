# expose tasks for discovery by django_celery
from datetime import timedelta, datetime

from websecmap.app.models import create_job, Job  # noqa  # pylint: disable=unused-import
from websecmap.organizations.models import GenericFileDataset, Dataset
from websecmap.scanners.models import TlsQualysScratchpad, PlannedScan, PlannedScanStatistic, InternetNLV2Scan
from websecmap.map.models import MapDataCache
from websecmap.api.models import SIDNUpload
from websecmap.celery import app, EXPIRES_IN_ONE_DAY


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def clean_application_caches_and_logs(retention_days: int = 30):
    """
    Why no truncation and optimization:
    # This is not used because its nicer to have more certainty as in: i always want to look at stuff from the last 30
    # days. Instead of, it might have been deleted yesterday, or the 'first of the month'. It's easier to work with
    # everything from the last 30 days is here. And we can then just run this every day, instead of slowing down
    # everything massively because a lot has to be deleted. It's also less disk space to reclaim with optimize table
    # commands and such... so less disk space lost if we don't optimize it at all (which we wont because the ORM
    # doesnt understand it and it's tricky to do otherwise).
    """

    days_back = datetime.now() - timedelta(days=retention_days)

    # todo: mapdatacache should be synced to disk. Would be faster for retrieval and storage.
    tables_to_reduce = [
        {
            "model": Job,
            "time_column": "created_on",
        },
        {
            "model": TlsQualysScratchpad,
            "time_column": "at_when",
        },
        {
            "model": PlannedScan,
            "time_column": "requested_at_when",
        },
        {
            "model": PlannedScanStatistic,
            "time_column": "at_when",
        },
        {
            "model": InternetNLV2Scan,
            "time_column": "created_at_when",
        },
        # We're not removing MapDataCaches, because if browsing in the past becomes easier, these caches have to
        # be rebuilt every day when they are requested.
        # {
        #     "model": MapDataCache,
        #     "time_column": "cached_on",
        # },
        {
            "model": SIDNUpload,
            "time_column": "at_when",
        },
        {
            "model": GenericFileDataset,
            "time_column": "imported_on",
        },
        {
            "model": Dataset,
            "time_column": "imported_on",
        },
    ]

    for info in tables_to_reduce:
        info["model"].objects.all().filter(**{f"{info['time_column']}__lte": days_back}).delete()
