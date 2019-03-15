from websecmap.map.management.commands.calculate_high_level_statistics import CalculateCommand
from websecmap.map.report import calculate_map_data


class Command(CalculateCommand):
    CalculateCommand.command = calculate_map_data
