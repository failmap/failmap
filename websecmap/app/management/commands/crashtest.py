import logging
from datetime import datetime

import pytz
from constance import config
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization, OrganizationType, Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Runs various live scans and requests as a long integration test. It's reliable to check for missing includes
    and other code that crashed when loading or running. It is not a complete test per scanner / per function. And
    it requires internet connectivity for a lot of the scans.

    It also requires devserver to be running.

    todo: in the future, move this test-set to the tests folder.
    """

    help = __doc__

    def handle(self, *args, **options):
        if not settings.DEBUG:
            log.error("Not running in debug mode. Given risky operations, this code will not run now.")
            # todo: move to test environment.

        try:
            log.info("Setting up test-data.")
            organization_type, organization, url, configuration = setup()

            log.info("Testing app commands")
            test_app_commands()

            log.info("Testing map commands")
            test_map_commands(organization, url)

            log.info("Testing organization commands, this can take a while.")
            test_organization_commands(organization)

            log.info("Testing scanner commands, which can take a while.")
            test_commandline_scanners(url)

            log.info("Testing map views")
            test_map_views(organization_type, organization)

        except KeyboardInterrupt:
            log.info("Received interrupt. Quitting.")


def test_map_views(organization_type, organization):
    """
    Tests all urls on the map, to see if it loads / does not crash etc.

    The correctness of each of these views is not validated. It could be utter garbage.

    For this devserver needs to be running.

    Todo: how is this done in other tests? -> via a docker IP. So these tests will have to be rewritten.
    """
    from django.test.client import RequestFactory

    rf = RequestFactory()
    request = rf.get("/")
    request.csrf_processing_done = True
    request.META["HTTP_HOST"] = "127.0.0.1"
    request.LANGUAGE_CODE = "NL"

    # autofill known parameters with some generic values:
    autofill = {
        "organization_type_name": organization_type.name,
        "country": organization.country,
        "organization_type": organization_type.name,
        "days_back": 0,
        "weeks_duration": 0,
        "weeks_back": 0,
        "organization_id": organization.id,
        "displayed_issue": "",  # todo: all the known issues from scanners
        "scan_type": "plain_https",  # todo: all known scans
        "request": request,
        "parameter": "",
        "args": {},  # LatestScanFeed
        "kwargs": {"scan_type": "plain_https"},  # LatestScanFeed
        "file_format": "json",
        "organization_name": organization.name,
        "url": "http://localhost:8000/",
        "requests_args": {"params": {"access_token": config.MAPBOX_ACCESS_TOKEN}},
    }

    import inspect

    from websecmap.map.urls import urlpatterns

    for pattern in urlpatterns:

        # can't test this, also part of django, so why test it here?
        if pattern.name == "javascript-catalog":
            continue

        callback = pattern.callback
        log.debug("Testing: %s" % callback)
        arguments = inspect.signature(callback).parameters.keys()

        kwargs = {}
        for argument in arguments:
            kwargs[argument] = autofill[argument]

        output = callback(**kwargs)
        log.debug("Received: %s" % output.content[0:80])


def test_app_commands():
    call_debug_command("translate")
    call_debug_command("ver")

    # celery tested in test cases
    # call_debug_command('celery')

    # ignore devserver, we use that all day, every day
    # test_dataset is run during build.
    # production is used in production, so well...


def test_map_commands(organization, url):
    # todo: also test game in next game iteration
    # this is going to take a while
    call_debug_command("rebuild_reports", "-o", organization.name)
    call_debug_command("report", "-o", organization.name)
    call_debug_command("timeline", "-u", url.url)

    call_debug_command("calculate_map_data", "--days", "1")
    call_debug_command("calculate_vulnerability_graphs", "--days", "1")
    call_debug_command("check_default_ratings")
    call_debug_command("clear_cache")
    call_debug_command("clear_ratings")
    call_debug_command("import_coordinates", "--list")
    call_debug_command("import_coordinates", "--country", "NL", "--region", "province")
    call_debug_command("update_coordinates", "--country", "NL", "--region", "province")


def test_organization_commands(organization):
    call_debug_command("add_urls", "-u", "doesnotresolve.faalkaart.nl")
    call_debug_command("export_organization", "--include_generated", organization.name)

    call_debug_command("clean_short_outages")

    call_debug_command("reset_autocomputed_fields_in_urls")
    call_debug_command("update_datamodel_documentation")

    call_debug_command("create_test_dataset", "--output", "failmap_test_dataset_test")
    call_debug_command("create_debug_dataset", "--output", "failmap_debug_dataset_test")
    call_debug_command("create_dataset", "--output", "failmap_dataset_test")

    # will not test clear_database, because of disasterous consequences. Could be done in test-database.
    # todo: move to real test environment. Do we have network there? How do we get packages? So yes?
    # call_debug_command('clear_database')
    # call_debug_command('load_dataset', 'failmap_dataset_test')


def test_commandline_scanners(url):
    # Calls all scanner commands, except the ones prefixed with one_shot (as they will be removed in the future)

    call_debug_command("check_network")
    call_debug_command("reset_onboards")
    call_debug_command("forward_onboards")

    # will not perform any db action without the --accept parameter
    # failmap revive endpoint 2018-10-15
    call_debug_command("revive", "endpoints", "2018-10-15")
    call_debug_command("revive", "urls", "2018-10-15")

    from websecmap.scanners.management.commands.discover import scanners

    for scanner in scanners:
        call_debug_command("discover", scanner, "-u", url.url)

    from websecmap.scanners.management.commands.verify import scanners

    for scanner in scanners:
        call_debug_command("verify", scanner, "-u", url.url)

    from websecmap.scanners.management.commands.scan import scanners

    for scanner in scanners:
        call_debug_command("scan", scanner, "-u", url.url)

    call_debug_command("set_latest_scan")


def call_debug_command(command_name, *args):
    log.warning("Calling command: %s %s" % (command_name, " ".join(args)))
    call_command(command_name, *args)


def setup():

    # Make a test organization + url
    test_type = OrganizationType.objects.all().filter(name="test").first()

    if not test_type:
        test_type = OrganizationType()
        test_type.name = "test"
        test_type.save()

    # Make sure the test organization can be scanned etc
    test_organization = Organization.objects.all().filter(name="test").first()

    if not test_organization:
        test_organization = Organization()
        test_organization.name = "test"
        test_organization.created_on = datetime.now(pytz.utc)
        test_organization.country = "NL"
        test_organization.internal_notes = "Created for testing purposes only."
        test_organization.type = test_type
        test_organization.save()

    test_url = Url.objects.all().filter(organization=test_organization).first()

    if not test_url:
        test_url = Url()
        test_url.url = "faalkaart.nl"
        test_url.save()

        test_url.organization.add(test_organization)
        test_url.save()

    # make sure the test organization can be scanned, doesn't have to be displayed on the map or something.
    configuration = Configuration.objects.all().filter(country="NL", organization_type=test_type).first()
    if not configuration:
        configuration = Configuration()
        configuration.organization_type = test_type
        configuration.country = "NL"
        configuration.is_reported = True
        configuration.is_scanned = True
        configuration.is_displayed = False
        configuration.is_the_default_option = False
        configuration.save()

    return test_type, test_organization, test_url, configuration
