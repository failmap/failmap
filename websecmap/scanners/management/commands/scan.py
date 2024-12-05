from inspect import signature
from collections import defaultdict
from websecmap.app.management.commands._private import ScannerTaskCommand
from websecmap.scanners import tasks
from websecmap.scanners.management.commands import ActionCommand

IGNORE = ["organizations_filter", "urls_filter", "endpoints_filter", "args", "kwargs", "urls"]


# don't know if the taskcommand stuff clashes
class Command(ScannerTaskCommand, ActionCommand):
    scanners = {x.__name__.split(".")[-1]: x for x in tasks.__scanners__ if hasattr(x, "compose_manual_scan_task")}

    scanner_arguments = {}
    scanners_arguments = defaultdict(list)

    def add_arguments(self, parser):
        for name, scanner in self.scanners.items():
            sig = signature(scanner.compose_manual_scan_task)

            group = parser.add_argument_group(f"{name} options")

            for parameter in sig.parameters.values():
                if parameter.name in IGNORE:
                    continue
                if not parameter.default:
                    continue

                group.add_argument(f"--{parameter.name}", type=type(parameter.default))
                self.scanners_arguments[name].append(parameter.name)

        super().add_arguments(parser)

    def handle(self, *args, **options):
        scanner_name = options["scanner"][0]
        for argument in self.scanners_arguments[scanner_name]:
            if options.get(argument) is not None:
                self.scanner_arguments[argument] = options.get(argument)

        return super().handle(self, *args, **options)
