import logging

from django.core.management.base import BaseCommand

from failmap.organizations.sources import dutch_government

log = logging.getLogger(__package__)


importers = {
    'dutch_government': dutch_government,
}


class Command(BaseCommand):
    """
    Specify an importer and you'll be getting all organizations you'll ever dream of
    """

    def add_arguments(self, parser):
        parser.add_argument('importer', nargs=1, help='The importer you want to use.', choices=importers)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options['importer'][0] not in importers:
                print("Importer does not exist. Please specify a valid importer from this list: %s " % importers.keys())
                return

            importer_module = importers[options['importer'][0]]
            importer_module.import_datasets()

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
