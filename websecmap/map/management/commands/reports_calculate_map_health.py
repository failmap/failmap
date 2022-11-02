import logging
from typing import List

from websecmap.map.logic.map_health import update_map_health_reports
from websecmap.map.management.commands.custom_commands import CalculateCommand
from websecmap.scanners.scanmetadata import get_backend_scanmetadata

log = logging.getLogger(__package__)


def _update_map_health_reports(days: int = 366, countries: List = None, organization_types: List = None):
    metadata = get_backend_scanmetadata()

    update_map_health_reports(
        metadata["published_scan_types"], days=days, countries=countries, organization_types=organization_types
    )


class Command(CalculateCommand):
    CalculateCommand.command = _update_map_health_reports
