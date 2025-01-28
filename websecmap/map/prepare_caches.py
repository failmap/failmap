from websecmap.celery import app
from websecmap.map.logic.map_health import update_map_health_reports
from websecmap.map.report import calculate_high_level_stats, calculate_map_data, calculate_vulnerability_statistics
from websecmap.scanners.scanmetadata import get_backend_scanmetadata


@app.task(queue="kickoff")
def prepare_daily_caches_for_everything():
    metadata = get_backend_scanmetadata()
    tasks = []
    tasks += calculate_vulnerability_statistics(1)
    tasks += calculate_map_data(1)
    tasks += calculate_high_level_stats(1)
    tasks += update_map_health_reports(metadata["published_scan_types"], 1)
    for task in tasks:
        task.apply_async()
