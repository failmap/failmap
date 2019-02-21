import logging

from django.core.management.base import BaseCommand
from django.db.models import Count

from websecmap.organizations.models import Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Specify an importer and you'll be getting all organizations you'll ever dream of
    """

    def handle(self, *args, **options):
        double_urls = Url.objects.values('url').annotate(num_urls=Count('url')).order_by().filter(num_urls__gt=1)

        log.debug("%s duplicate urls: %s" % (len(double_urls), double_urls))

        # keep the oldest:
        for double_url in double_urls:
            log.debug("%s: %s" % (double_url['url'], double_url['num_urls']))
            # - = descending, so, not using - is ascending, which is from small to large. Which is what we need.
            all_doubles = list(Url.objects.all().filter(url=double_url['url']).order_by('created_on'))

            Url.objects.all().filter(url=double_url['url']).exclude(pk=all_doubles[0].pk).delete()
