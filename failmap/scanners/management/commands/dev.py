import logging

from django.core.management.base import BaseCommand

from failmap.map.rating import (add_organization_rating, create_timeline, rerate_urls,
                                show_timeline_console)
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        return
        # develop_determineratings()
        # test_can_connect_to_organization()
        # as a task
        # develop_determineratings()

        # reset_onboard()
        # rebuild_ratings()
        # develop_determineratings()
        # develop_timeline()
        #
        # Command.test_sslscan_real()
        # Command.test_determine_grade()
        # Command.develop_sslscan()
        # Command.develop_celery()
        # Command.develop_celery_advanced()
        # Command.develop_celery_test_async_tasks()


def reset_onboard():
    organization = Organization.objects.filter(name="Arnhem").get()
    urls = Url.objects.all().filter(organization=organization)
    for url in urls:
        url.onboarded = False
        url.save()


def develop_timeline():

    if True:
        organization = Organization.objects.filter(name="Internet Cleanup Foundation").get()
        urls = Url.objects.all().filter(organization=organization)
        for url in urls:
            data = create_timeline(url=url)
            show_timeline_console(data, url)
            rerate_urls([url])
        add_organization_rating(organizations=[organization], create_history=True)

    if False:
        organizations = Organization.objects.all().order_by('name')
        for organization in organizations:
            rerate_urls(Url.objects.all().filter(organization=organization))

    if False:
        # url = Url.objects.all().filter(url='www.amersfoort.nl').get()
        # url = Url.objects.all().filter(url='sip.arnhem.nl').get()

        # is deleted over time. has to receive a final empty rating.
        # url = Url.objects.all().filter(url='formulieren.hengelo.nl').get()

        # had empty ratings, while relevant
        # url = Url.objects.all().filter(url='mijnoverzicht.alphenaandenrijn.nl').get()

        # has ratings on a ton of redundant endpoints.
        url = Url.objects.all().filter(url='webmail.zaltbommel.nl').get()
        url = Url.objects.all().filter(url='geo.aaenhunze.nl').get()
        url = Url.objects.all().filter(url='webserver03.bloemendaal.nl').get()
        data = create_timeline(url=url)
        show_timeline_console(data, url)
        rerate_urls([url])

        # OrganizationRating.objects.all().delete()
        # for organization in url.organization.all():
        #     rate_organization_efficient(organization=organization, create_history=True)


def develop_sslscan():
    from failmap.scanners.scanner_tls_standalone import scan_url
    url = Url.objects.all().filter(url='www.ibdgemeenten.nl').get()
    scan_url(url)
    url = Url.objects.all().filter(url='www.amersfoort.nl').get()
    scan_url(url)


def test_determine_grade():
    from failmap.scanners.scanner_tls_standalone import test_determine_grade
    test_determine_grade()


def test_sslscan_real():
    from failmap.scanners.scanner_tls_standalone import test_real
    test_real('johnkr.com', 443)


def develop_celery_advanced():
    url = Url.objects.all().filter(url='www.ibdgemeenten.nl').get()
    http_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='http')
    https_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='https')
    endpoints = list(http_endpoints) + list(https_endpoints)
    eps = []
    for endpoint in endpoints:
        if endpoint.is_ipv4():
            eps.append(endpoint)

    # for endpoint in eps:
    #     dispatch_scan_security_headers(endpoint)


def develop_determineratings():
    # DetermineRatings.default_ratings()
    # return
    from datetime import datetime
    import pytz
    from failmap.map.rating import relevant_endpoints_at_timepoint

    u = Url.objects.all().filter(url='www.arnhem.nl').get()
    relevant_endpoints_at_timepoint(url=u, when=datetime(2016, 12, 31, 0, 0, tzinfo=pytz.utc))
    # DetermineRatings.significant_times(organization=organization)
    # urls = Url.objects.all().filter(organization=organization)
    # for url in urls:
    #     DetermineRatings.get_url_score_modular(url)

    # pyflakes when = datetime(2016, 12, 31, 0, 0, tzinfo=pytz.utc)
    # when = datetime.now(pytz.utc)
    # organization = Organization.objects.filter(name="Zederik").get()
    # rerate_urls(Url.objects.all().filter(organization=organization))
    # rerate_organizations(organizations=[organization])
    # ratings are always different since we now also save last scan date.
    # only creates things for near midnight. Should check if today, and then save for now.
    # add_organization_rating(organization, create_history=True)
    # create one for NOW, not this night. This is a bug :)
    # add_organization_rating(organization)


def test_can_connect_to_organization():
    from failmap.scanners.scanner_http import can_connect, get_ips
    organization = Organization.objects.filter(name="Zederik").get()
    urls = Url.objects.all().filter(organization=organization)
    for url in urls:
        ipv4, ipv6 = get_ips(url.url)
        if ipv4:
            logger.info(can_connect("http", url, 80, ipv4))
        if ipv6:
            logger.info(can_connect("http", url, 80, ipv6))
