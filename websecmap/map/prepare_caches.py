from websecmap.scanners.scanmetadata import get_backend_scanmetadata
from websecmap.map.report import (
    calculate_vulnerability_statistics,
    calculate_map_data,
    calculate_high_level_stats,
)
from websecmap.map.logic.map_health import update_map_health_reports
from celery import group


def compose_task(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None):
    metadata = get_backend_scanmetadata()

    # Chaining this subtask costs an insane amount of memory, as each task will have this subtask attached to it.
    # Just adding it to the task list does not guarantee execution order _after_ the reporting tasks.
    # so to reduce memory this has become a separate task which is run at a different time than reporting.
    # just to fill up caches and speed things up
    # todo: how to maintain sequence?

    # finally, rebuild the graphs (which can mis-matchi a bit if the last reports aren't in yet. Will have to do for now
    # mainly as we're trying to get away from canvas and it's buggyness.

    subtasks = []
    # These are database heavy tasks, and executed sequentially to spread load on the database.
    if organizations_filter.get("country__in", None):
        subtasks.append(
            calculate_vulnerability_statistics.si(1, organizations_filter["country__in"])
            | calculate_map_data.si(1, organizations_filter["country__in"])
            | calculate_high_level_stats.si(1, organizations_filter["country__in"])
            | update_map_health_reports.si(metadata["published_scan_types"], 1, organizations_filter["country__in"])
        )
    elif organizations_filter.get("country", None):
        subtasks.append(
            calculate_vulnerability_statistics.si(1, [organizations_filter["country"]])
            | calculate_map_data.si(1, [organizations_filter["country"]])
            | calculate_high_level_stats.si(1, [organizations_filter["country"]])
            | update_map_health_reports.si(metadata["published_scan_types"], 1, [organizations_filter["country"]])
        )
    else:
        subtasks.append(
            calculate_vulnerability_statistics.si(1)
            | calculate_map_data.si(1)
            | calculate_high_level_stats.si(1)
            | update_map_health_reports.si(metadata["published_scan_types"], 1)
        )

    return group(subtasks)
