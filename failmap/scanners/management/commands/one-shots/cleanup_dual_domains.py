import logging

from django.core.management.base import BaseCommand

from failmap.scanners.models import Endpoint, Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Cleans up duiven.n.duiven.nl domains, created due to a bug.'

    """
    You probably don't need to run this anymore...
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        endpoints = Endpoint.objects.all().filter(url__url__regex=".*\.n\..*\..*")

        for endpoint in endpoints:
            log.debug("Found possible weird endpoint: %s" % endpoint)
            # endpoint.delete()

        urls = Url.objects.all().filter(url__iregex=".*\.n\..*\..*")

        for url in urls:
            log.debug("Found possible weird url: %s" % url)
            # url.delete()
