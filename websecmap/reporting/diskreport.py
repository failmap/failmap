"""
Reports are stored to disk and retrieved from disk transparently using the fasted JSON library we can find.

Reports can be stored in various formats, where the "original" is the original from websecmap. A variant might be
added without detailed findings for example.
"""
import gzip
import json
import logging

from django.db.models import Model
from django.conf import settings

from websecmap.map.models import OrganizationReport

log = logging.getLogger(__package__)


def get_original_storage_location():
    return f"{settings.REPORT_STORAGE_DIR}/original/"


def sync_reports_from_db_to_disk(model: "Model" = OrganizationReport):
    """
    Copies all reports to disk and deletes them from the database.

    Don't forget to optimize tables afterwards otherwise disk space is not reclaimed.
    """
    for report in model.objects.all().only("id"):
        sync_report_from_db_to_disk(report.id, model)


def sync_report_from_db_to_disk(report_id: int, model: "Model" = OrganizationReport):
    # Moves a report to file and deletes the report data from the database.
    report = model.objects.all().filter(id=report_id).first()
    if not report.calculation:
        log.debug("Report contains no data (anymore), not syncing it to disk.")
        return

    filename = f"{get_original_storage_location()}{report_id}.gson"
    write_json_to_gzip(filename, report.calculation)
    report.calculation = None
    report.save()


def write_json_to_gzip(location, content):
    with gzip.open(location, "wt") as file:
        file.write(json.dumps(content))


def read_json_from_gzip(location):
    with gzip.open(location, "rt") as file:
        return json.loads(file.read())
