import logging

from django.core.management.base import BaseCommand

from failmap.map.rating import (add_organization_rating, create_timeline, inspect_timeline,
                                rebuild_url_ratings)
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        test_osaft()
        return

        # tasking()
        # develop_determineratings()
        # test_can_connect_to_organization()
        # as a task
        # develop_determineratings()

        # reset_onboard()
        # rebuild_ratings()
        # develop_determineratings()
        # develop_timeline()

        # Command.test_sslscan_real()
        # Command.test_determine_grade()
        # Command.develop_sslscan()
        # Command.develop_celery()
        # Command.develop_celery_advanced()
        # Command.develop_celery_test_async_tasks()


def test_osaft():
    from failmap.scanners.scanner.tls_osaft import scan_address, determine_grade, grade_report, scan_url
    from failmap.scanners.scanner.scanner import q_configurations_to_scan

    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
    ).order_by("?")

    for url in urls:
        scan_url(url)

    address = 'faalkaart.nl'
    port = 443
    report = scan_address(address, port)
    grades, trust = determine_grade(report)
    log.debug(trust)
    log.debug(grades)
    print(grade_report(grades, trust))


def rebuild_ratings():
    from failmap.map.rating import rebuild_organization_ratings

    organization = Organization.objects.filter(name="Arnhem").get()
    rebuild_url_ratings(list(Url.objects.all().filter(organization=organization)))
    rebuild_organization_ratings(organizations=[organization])


def tasking():
    from celery import group, chain

    group(chain(group(), group(), group())).apply_async()


def do_a_few_things():
    from failmap.scanners.tasks import every_two_minutes
    i = 30

    while i > 0:
        i -= 1
        every_two_minutes.s(i).apply_async()


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
            inspect_timeline(data, url)
            rebuild_url_ratings([url])
        add_organization_rating(organizations=[organization], create_history=True)

    if False:
        organizations = Organization.objects.all().order_by('name')
        for organization in organizations:
            rebuild_url_ratings(Url.objects.all().filter(organization=organization))

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
        inspect_timeline(data, url)
        rebuild_url_ratings([url])

        # OrganizationRating.objects.all().delete()
        # for organization in url.organization.all():
        #     rate_organization_efficient(organization=organization, create_history=True)


def develop_sslscan():
    from failmap.scanners.scanner.tls_standalone import scan_url
    url = Url.objects.all().filter(url='www.ibdgemeenten.nl').get()
    scan_url(url)
    url = Url.objects.all().filter(url='www.amersfoort.nl').get()
    scan_url(url)


def test_determine_grade():
    from failmap.scanners.scanner.tls_standalone import test_determine_grade
    test_determine_grade()


def test_sslscan_real():
    from failmap.scanners.scanner.tls_standalone import test_real
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
    # DetermineRatings.default_organization_rating()
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
    # rebuild_url_ratings(Url.objects.all().filter(organization=organization))
    # rebuild_organization_ratings(organizations=[organization])
    # ratings are always different since we now also save last scan date.
    # only creates things for near midnight. Should check if today, and then save for now.
    # add_organization_rating(organization, create_history=True)
    # create one for NOW, not this night. This is a bug :)
    # add_organization_rating(organization)
