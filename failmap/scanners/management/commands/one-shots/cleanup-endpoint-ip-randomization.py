import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap.scanners.models import Endpoint, Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Some endpoints have a different IP every day. In some cases this was built up, while' \
           'the endpoints where never declared dead: so at one point dozens of endpoints are seen' \
           'as dead. This script cleans up large chunks of endpoints that where declared dead at ' \
           'the same time. Be very careful of running this.'

    """
Example endpoints
URL                 Discsovered on              is dead since.
opendata.arnhem.nl	25 december 2016 22:45	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	25 december 2016 22:45	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	22 december 2016 21:54	28 augustus 2017 17:10	1
opendata.arnhem.nl	22 december 2016 21:54	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	21 december 2016 21:37	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	9 december 2016 18:01	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	9 december 2016 18:01	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	6 december 2016 16:56	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	6 december 2016 16:56	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	4 december 2016 15:50	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	4 december 2016 15:50	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	2 december 2016 15:01	s	28 augustus 2017 17:10	1
opendata.arnhem.nl	2 december 2016 15:01	28 augustus 2017 17:10	1
opendata.arnhem.nl	28 november 2016 13:42	28 augustus 2017 17:10	1

To

opendata.arnhem.nl	22 december 2016 21:54	25 december 2016 22:45	1
opendata.arnhem.nl	22 december 2016 21:54	s	22 december 2016 21:54	1
opendata.arnhem.nl	21 december 2016 21:37	s	22 december 2016 21:54	1
opendata.arnhem.nl	9 december 2016 18:01	s	21 december 2016 21:37	1
opendata.arnhem.nl	9 december 2016 18:01	s	21 december 2016 21:37	1
opendata.arnhem.nl	6 december 2016 16:56	s	9 december 2016 18:01	1
opendata.arnhem.nl	6 december 2016 16:56	s	9 december 2016 18:01	1
opendata.arnhem.nl	4 december 2016 15:50	s	6 december 2016 16:56	1
opendata.arnhem.nl	4 december 2016 15:50	s	6 december 2016 16:56	1
opendata.arnhem.nl	2 december 2016 15:01	s	4 december 2016 15:50	1
opendata.arnhem.nl	2 december 2016 15:01	4 december 2016 15:50	1
    """

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/

    def handle(self, *args, **options):
        # pyflakes endpoints = Endpoint.objects.all()

        # Command.urls_with_ridiculous_number_of_endpoints()
        Command.resequence_endpoint_deaths()

    @staticmethod
    # todo: does not account for ipv6.
    def resequence_endpoint_deaths():
        """Changes the is_dead_since dates in above example with a better sequenced one:
            The endpoint is dead once a new one has been discovered.

            Warning: do this only for the same protocol.

            opendata.arnhem.nl
            sites.zoetermeer.nl
            webmail.zaltbommel.nl
            webmail.gemeentemolenwaard.nl
            sites.almelo.nl
            pers.alkmaar.nl
        """
        url = Url.objects.all().filter(url="mail.rhenen.nl").get()
        log.debug("url %s" % url)
        endpoints = Endpoint.objects.all().filter(url=url,
                                                  protocol="https",
                                                  port="443").order_by('discovered_on')
        for endpoint in endpoints:
            log.debug("endpoint: %s, Discovered on: %s" % (endpoint, endpoint.discovered_on))
            if endpoint.is_dead_since:
                log.debug('Would replace dead date %s' % endpoint.is_dead_since)
                try:
                    endpoint.is_dead_since = Endpoint.objects.all().filter(
                        url=url,
                        discovered_on__gt=endpoint.discovered_on).earliest('discovered_on').\
                        discovered_on
                    log.debug('With date: %s' % endpoint.is_dead_since)
                    endpoint.save()
                except ObjectDoesNotExist:
                    log.warning('Not replaced at all, since there is no date before this.')

    @staticmethod
    def urls_with_ridiculous_number_of_endpoints(protocol="https"):
        """
        Warning: this is just an indication! This does not have to be true.

        Note that most SIP sites have 6 endpoints. Some provider does that.

        :param protocol:
        :return:
        """
        from django.db.models import Count
        # can't filter on annotations.
        urls = Url.objects.all().filter(endpoint__protocol__exact=protocol).annotate(
            count_endpoints=Count('endpoint'))
        ridiculous_urls = []

        for url in urls:
            if url.count_endpoints > 6:
                ridiculous_urls.append(url)

        for ridiculous_url in ridiculous_urls:
            log.debug("Ridiculous amount of endpoints on: %s" % ridiculous_url)
            log.debug("You are looking for the ones that have _a lot_ of the same Is dead Since")
            endpoints = Endpoint.objects.all().filter(url=ridiculous_url)
            for endpoint in endpoints:
                log.debug("Is dead since: %s, Endpoint: %s," %
                          (endpoint.is_dead_since, endpoint))

        return ridiculous_urls
