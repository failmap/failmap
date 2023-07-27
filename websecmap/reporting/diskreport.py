"""
Reports are stored to disk and retrieved from disk transparently using the fasted JSON library we can find.

Reports can be stored in various formats, where the "original" is the original from websecmap. A variant might be
added without detailed findings for example.
"""
from json import JSONDecodeError

import gzip
import json
import logging
import os
from typing import Dict, Type, Union

from django.conf import settings

# Models import is used in type hints
from django.db.models import Model  # pylint: disable=unused-import

from websecmap.map.models import OrganizationReport

log = logging.getLogger(__package__)


def store_report(report_id: Union[int, str], model: str = "OrganizationReport", data: Dict = None):
    if data is None:
        data = {}
    return _write_json_to_gzip(location_on_disk(report_id, model), data)


def retrieve_report(report_id: Union[int, str], model: Union[str, Type["Model"]] = "OrganizationReport"):
    return _read_json_from_gzip(location_on_disk(report_id, model))


def location_on_disk(report_id: Union[int, str], model: Union[str, Type["Model"]] = "OrganizationReport"):
    # prevent some path traversal and directory issues, but not all:
    report_id = str(report_id).replace(".", "").replace("/", "").replace("\\", "")

    # because of the 500.000 reports on basisbeveiliging, which take 100 gigabyte, we should use some sort of mapping
    # that create subdirectories per 1000 files or so. Otherwise administration with linux tools is too slow.
    if len(report_id) <= 3:
        return f"{storage_location_of_model(model)}/{report_id}.gson"

    # Any report ids larger than 999 (or fff) will get their own subdirectory based on their first 3 characters:
    subdirectory = report_id[:3]
    subdir_storage_directory = f"{storage_location_of_model(model)}/{subdirectory}/"
    if not os.path.isdir(subdir_storage_directory):
        os.makedirs(subdir_storage_directory, exist_ok=True)

    return f"{storage_location_of_model(model)}/{subdirectory}/{report_id}.gson"


def storage_location_of_model(model: Union[str, Type["Model"]] = "OrganizationReport"):
    model_name = model if isinstance(model, str) else model.__name__
    return f"{get_original_storage_location()}{model_name}"


def get_original_storage_location():
    return f"{settings.REPORT_STORAGE_DIR}/original/"


def sync_reports_from_db_to_disk(model: Type["Model"] = OrganizationReport, limit: int = 10000000):
    """
    Copies all reports to disk and deletes them from the database.

    Don't forget to optimize tables afterwards otherwise disk space is not reclaimed.
    """

    for report in model.objects.all().only("id")[:limit]:
        sync_report_from_db_to_disk(report.id, model)


def sync_report_from_db_to_disk(report_id: int, model: Type["Model"] = OrganizationReport):
    # Moves a report to file and deletes the report data from the database.
    report = model.objects.all().filter(id=report_id).first()
    if report.calculation is None:
        log.debug("Report contains no data (anymore), not syncing it to disk.")
        return

    os.makedirs(storage_location_of_model(model), exist_ok=True)

    _write_json_to_gzip(location_on_disk(report_id, model), report.calculation)

    report.calculation = None
    report.save()


def _write_json_to_gzip(location, content):
    # Just crash horribly when the disk is full.
    # log.debug(f"Writing report file: {location}")
    with gzip.open(location, "wt") as file:
        file.write(json.dumps(content))


def _read_json_from_gzip(location):
    try:
        # log.debug(f"Reading report file: {location}")
        with gzip.open(location, "rt") as file:
            return json.loads(file.read())
    except FileNotFoundError:
        log.info("Report does not exist on location %s.", location)
        return {}
    except JSONDecodeError:
        # this is weird, should not happen. Don't crash.
        log.error(f"Report does not contain valid json, {location}.", location)
        return {}
    except Exception as e:
        # Possibly corrupted gzip file, this might happen for whatever reason.
        # Error -3 while decompressing data: invalid stored block lengths
        log.exception("Other error occurred when reading report from %s: %s", location, e)
        return {}
