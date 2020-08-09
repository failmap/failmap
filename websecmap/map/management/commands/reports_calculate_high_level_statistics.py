from websecmap.map.management.commands.custom_commands import CalculateCommand
from websecmap.map.report import calculate_high_level_stats


class Command(CalculateCommand):
    CalculateCommand.command = calculate_high_level_stats
