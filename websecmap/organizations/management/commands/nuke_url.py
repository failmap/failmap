import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.nuke import nuke_url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    # websecmap nuke_url --url zupthen --suffix nl --exclude_subdomains test abc hallo
    # Nuking url zupthen, with suffix nl, exlcuding ['test', 'abc', 'hallo']

    def add_arguments(self, parser):
        parser.add_argument("--url", nargs=1, help="The url, computed_domain. example in example.nl")
        parser.add_argument("--suffix", nargs="?", help="The suffix, computed_suffix, nl in example.nl")
        parser.add_argument("--exclude_subdomains", nargs="*", help="List of subdomains that will not be deleted")
        super().add_arguments(parser)

    def handle(self, *args, **options):
        url = options.get("url", [])[0]
        tld = options.get("suffix")
        excluded_subdomains = options.get("exclude_subdomains")

        nuke_url(url, tld, excluded_subdomains=excluded_subdomains)
