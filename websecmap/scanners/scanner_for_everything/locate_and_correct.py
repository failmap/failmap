from celery import group

from websecmap.celery import app
from websecmap.scanners.scanner_for_everything.ip_geolocation_correction import create_tasks as correction_tasks
from websecmap.scanners.scanner_for_everything.location import create_tasks as location_tasks


@app.task(queue="kickoff")
def create_tasks() -> group:
    group(
        [
            location_tasks()
            |
            # also autocorrect, to prevent a ping-pong between correct and incorrect records.
            # There should be minimal time between measuring and correcting.
            # todo: the correction should be done IN the location code, not separately. This is just a workaround.
            correction_tasks()
        ]
    ).apply_async()

    return group()
