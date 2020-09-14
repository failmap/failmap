import logging
from typing import List

from websecmap.map.logic.map_health import update_map_health_reports
from websecmap.map.management.commands.custom_commands import CalculateCommand
from websecmap.map.report import PUBLISHED_SCAN_TYPES

log = logging.getLogger(__package__)


def _update_map_health_reports(days: int = 366, countries: List = None, organization_types: List = None):
    update_map_health_reports(
        PUBLISHED_SCAN_TYPES, days=days, countries=countries, organization_types=organization_types
    )


class Command(CalculateCommand):
    CalculateCommand.command = _update_map_health_reports
