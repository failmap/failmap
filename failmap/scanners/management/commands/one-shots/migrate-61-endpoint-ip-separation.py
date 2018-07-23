import logging

from django.core.management.base import BaseCommand

from failmap.scanners.models import Endpoint, EndpointGenericScan, Screenshot, TlsQualysScan, UrlIp

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Make the migration of issue 61: place IP addresses in a separate table'

    def handle(self, *args, **options):

        move_ip_information()
        merge_duplicate_endpoints()

        # Step: verify that everything works
        # rebuild-ratings: still works exactly the same, with the same bugs.
        #   todo: history slider does not change report over time. Also on original.
        # scanners should work differently: ip has to be stored separately.
        # life-cycle of discovery changes completely.


def move_ip_information():
    """
    Step 1

    This is pretty straight forward: create IP records in a new table, pointing to the old
    endpoints. Take over the same information about existance (or non-existance) and just delete
    the IP information.

    :return:
    """

    endpoints = Endpoint.objects.all()

    for endpoint in endpoints:
        epip = UrlIp()
        epip.url = endpoint.url
        epip.ip = endpoint.ip
        epip.discovered_on = endpoint.discovered_on
        epip.is_unused = endpoint.is_dead
        epip.is_unused_reason = endpoint.is_dead_reason
        epip.is_unused_since = endpoint.is_dead_since
        epip.save()

        endpoint.ip_version = 6 if ":" in endpoint.ip else 4
        endpoint.ip = ""  # and it's gone.
        endpoint.save()

    # deduplicate the same urls:

    epips = UrlIp.objects.all()
    for epip in epips:
        UrlIp.objects.all().filter(url=epip.url, ip=epip.ip).exclude(id=epip.id).delete()


"""
Going back:
rm db.sqlite3
failmap migrate
failmap createsuperuser

failmap clear-database
failmap load-dataset testdata  # we've not deleted columns till here.
failmap rebuild-ratings
failmap migrate-61-endpoint-ip-separation
failmap rebuild-ratings

failmap clear-database && failmap load-dataset productiondata &&
failmap migrate-61-endpoint-ip-separation && failmap rebuild-ratings

# The ratings should be the same
"""


def merge_duplicate_endpoints():
    """
    Step 2

    This is the hard part, as it reduces the amount of endpoints significantly.

    Well, it doesn't look that hard now that it's implemented. Thank you Django.

    :return:
    """

    # ordered by newest first, so you'll not have to figure out the current is_dead situation.
    endpoints = Endpoint.objects.all().order_by("-discovered_on")

    for endpoint in endpoints:

        # check if this endpoint still exists... it could be deleted in a previous check
        # it can mess up connecting deleted endpoints
        if not Endpoint.objects.filter(id=endpoint.id).exists():
            log.debug('Endpoint does not exist anymore, probably merged previously. Continuing...')
            continue

        log.debug("Endpoint: %s, Discovered on: %s" % (endpoint, endpoint.discovered_on))
        similar_endpoints = list(Endpoint.objects.all().filter(
            ip_version=endpoint.ip_version,
            port=endpoint.port,
            protocol=endpoint.protocol,
            url=endpoint.url).exclude(id=endpoint.id).order_by('-discovered_on'))

        # In some cases there are hundreds of endpoints due to IP switching.
        # Using the first one, we can determine from when the endpoint existed.
        # This is relevant for creating reports.
        # EX:
        """
        URL                 DOMAIN              DISCOVERED ON       ipv PORT PROTOCOL IS DEAD SINCE     TLS SCAN COUNT
        ... and 200 more...

        opendata.arnhem.nl	opendata.arnhem.nl	27 april 2016 14:59	4	443	https	3 mei 2016 03:18	1
        opendata.arnhem.nl	opendata.arnhem.nl	27 april 2016 14:59	4	443	https	3 mei 2016 03:18	1
        opendata.arnhem.nl	opendata.arnhem.nl	27 april 2016 14:59	4	443	https	3 mei 2016 03:18	1
        opendata.arnhem.nl	opendata.arnhem.nl	8 april 2016 19:52	4	443	https	27 april 2016 14:59	1
        opendata.arnhem.nl	opendata.arnhem.nl	8 april 2016 19:52	4	443	https	27 april 2016 14:59	1
        """
        if similar_endpoints:
            first_similar = similar_endpoints[-1]
            log.debug("Last similar: %s, Discovered on: %s" % (first_similar, first_similar.discovered_on))
            endpoint.discovered_on = first_similar.discovered_on
            endpoint.save()
        else:
            log.debug("There are no similar endpoints. Ignoring.")

        for similar_endpoint in similar_endpoints:
            # apperantly exclude doesn't work... there goes my faith in the data layer.
            if similar_endpoint == endpoint:
                continue

            # migrate all scans to the same endpoint
            log.debug("Merging similar: %s, Discovered on: %s" % (similar_endpoint, similar_endpoint.discovered_on))
            EndpointGenericScan.objects.all().filter(endpoint=similar_endpoint).update(endpoint=endpoint)
            TlsQualysScan.objects.all().filter(endpoint=similar_endpoint).update(endpoint=endpoint)
            Screenshot.objects.all().filter(endpoint=similar_endpoint).update(endpoint=endpoint)

            # goodbye
            similar_endpoint.delete()
