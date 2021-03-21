from websecmap.map.management.commands.custom_commands import CalculateCommand
from websecmap.map.report import calculate_map_data


class Command(CalculateCommand):
    CalculateCommand.command = calculate_map_data
