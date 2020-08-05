# https://github.com/patrys/httmock
# https://github.com/spulec/freezegun

# install isort, experience it might have things different in tox :+
# pkg_resources.DistributionNotFound? -> tox -r (rebuild)
# running this test? env DJANGO_SETTINGS_MODULE=websecmap.settings
#   .tox/default/bin/pytest tests -k test_tls_scan_qualys
#

# todo: create rate_limit mock


import json

from colorama import Fore, Style, init
from freezegun import freeze_time
from httmock import HTTMock, response

from websecmap.scanners.models import Endpoint, TlsQualysScan
from websecmap.scanners.scanner import tls_qualys

try:
    # Python 3
    from urllib.parse import urlparse, parse_qs
except ImportError:
    # Python 2
    from urlparse import urlparse, parse_qs


# colorama's very generic init function. This is here to color messages on any platform.
init()


def generate_mock(domain="www.faalkaart.nl", grade="A", desired_response="READY"):
    response_dir = 'tests/tls_scan_qualys_responses/'
    headers = {'content-type': 'application/json'}

    print("%s%sMock answer: Grade %s, Response %s, Domain %s %s" %
          (Style.DIM, Fore.MAGENTA, grade, desired_response, domain, Style.RESET_ALL))

    content = {}

    if desired_response == "READY":
        content = json.loads(open(response_dir + 'www.faalkaart.nl.json').read())
        content["endpoints"][0]["gradeTrustIgnored"] = grade
        content["endpoints"][0]["grade"] = grade
        content["endpoints"][1]["gradeTrustIgnored"] = grade
        content["endpoints"][1]["grade"] = grade

    if desired_response == "ERROR":
        content = json.loads(open(response_dir + 'unable_to_resolve.json').read())
    if desired_response == "DNS":
        content = json.loads(open(response_dir + 'resolving_domain.json').read())
    if desired_response == "IN_PROGRESS":
        content = json.loads(open(response_dir + 'in_progress.json').read())

    content["host"] = domain
    return response(200, content, headers, None, 5)


def announce_testcase(casenumber, message):
    print()
    print(Fore.MAGENTA + "--- Testcase: %s ---------------------------------" % casenumber)
    print(message + Style.RESET_ALL)
    print()


# this is here to prevent "response object not callable"
def qualys_mock_b(url, request): return generate_mock("www.faalkaart.nl", "B")


def qualys_mock_a(url, request): return generate_mock("www.faalkaart.nl", "A")


def qualys_mock_c(url, request): return generate_mock("www.faalkaart.nl", "C")


def qualys_error_scan(url, request): return generate_mock("www.faalkaart.nl", "C", "ERROR")


# todo: als je een ander domein teruggeeft dan je opgeeft, dan gaat ie allerlei endpoints killen
# we are silently expecting that qualys will mirror the host
def qualys_mirror(url, request):
    """
    Request object looks like this:
    {'method': 'GET', 'url':
    'https://api.ssllabs.com/api/v2/analyze?host=www.faalkaart.nl&publish=off&startNew=off&
    fromCache=on&all=done', 'headers': {'User-Agent': 'python-requests/2.13.0', 'Accept-Encoding':
    'gzip, deflate', 'Accept': '*/*', 'Connection': 'keep-alive'}, '_cookies':
    <RequestsCookieJar[]>, 'body': None, 'hooks': {'response': []}, '_body_position': None,
    'original': <Request [GET]>}
    """

    url = request.url
    o = urlparse(url)
    query = parse_qs(o.query)
    domain = query['host'][0] if 'host' in query else 'www.youfailedit.com'
    return generate_mock(domain, "A")


# i have no clue on how to simulate several separate messages to the same mock object.
# we need that since the code tries a few times to get a result, where this result could
# change over time. We want to see that it does. We could randomize it, but that would
# not deliver a steady testcase. So we're abusing a singleton, rather have a nice clean solution.
class Counter:
    _count = 0

    def count(self):
        Counter._count += 1
        return Counter.count

    def reset(self):
        Counter._count = 0

    def value(self):
        return Counter._count


# Using a singleton to
def qualys_realistic_scan(url, request):
    Counter().count()

    if Counter().value() == 1:
        return generate_mock("www.faalkaart.nl", "A", "DNS")

    if Counter().value() == 2:
        return generate_mock("www.faalkaart.nl", "A", "IN_PROGRESS")

    if Counter().value() == 3:
        return generate_mock("www.faalkaart.nl", "A", "READY")

    if Counter().value() < 1 or Counter().value() > 3:
        raise ValueError('Counter for testcase not properly set up. Value: %s', Counter().value())


def test_tls_scan_qualys_sample_result(db):
    # 2017 09 15: the scanner checks on various headers, those are not emulated yet
    # so this test will always fail. We have to fake a webserver, with headers, that returns
    # various types of scan returns and the right headers.
    # until then, it's better to not run this test.
    return

    # nesting With's, hello VB Script :)
    announce_testcase(1, "Creating a new scan, where everything has to go right.")
    with freeze_time('2000-1-1', tick=True, tz_offset=1):
        with HTTMock(qualys_mock_a):
            tls_qualys.compose_manual_scan_task(urls_filter={'name__in': ["www.faalkaart.nl"]})
            assert Endpoint.objects.filter(domain="www.faalkaart.nl").count() == 2  # ipv4 + ipv6
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 2

    announce_testcase(2, "A new scan with the same result should not create additional endpoints"
                         "or scan results. Scan results would only be updated after 24h.")
    with freeze_time('2000-1-3', tick=True, tz_offset=1):
        with HTTMock(qualys_mock_a):
            tls_qualys.compose_manual_scan_task()(urls_filter={'name__in': ["www.faalkaart.nl"]})
            assert Endpoint.objects.filter(domain="www.faalkaart.nl").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 2

    announce_testcase(3, "When the rating changes for a scan result, but the rest stays the same"
                         "the number of endpoints should still be the same but the amount of scans"
                         "should increase as only changes are recorded.")
    with freeze_time('2000-1-5', tick=True, tz_offset=1):
        with HTTMock(qualys_mock_b):
            tls_qualys.compose_manual_scan_task()(urls_filter={'name__in': ["www.faalkaart.nl"]})
            assert Endpoint.objects.filter(domain="www.faalkaart.nl").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="B").count() == 2

    announce_testcase(4, "Performing a new scan within 24 hours does not change any result as the"
                         "scan is dismissed")
    with freeze_time('2000-1-5', tick=True, tz_offset=1):
        with HTTMock(qualys_mock_c):
            tls_qualys.compose_manual_scan_task()(urls_filter={'name__in': ["www.faalkaart.nl"]})
            assert Endpoint.objects.filter(domain="www.faalkaart.nl").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="B").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="C").count() == 0

    announce_testcase(5, "Verify that it's possible to scan multiple domains.")
    with freeze_time('2000-1-7', tick=True, tz_offset=1):
        with HTTMock(qualys_mirror):
            tls_qualys.compose_manual_scan_task()(
                urls_filter={
                    'name__in': [
                        "www.faalkaart.nl",
                        "www.elgerjonker.nl",
                        "www.nu.nl"]})

            assert Endpoint.objects.filter(domain="www.faalkaart.nl").count() == 2
            assert Endpoint.objects.filter(domain="www.elgerjonker.nl").count() == 2
            assert Endpoint.objects.filter(domain="www.nu.nl").count() == 2
            assert Endpoint.objects.filter(domain="www.youfailedit.com").count() == 0

            # Since there are (again) changes for faalkaart.nl, the count of A's is now higher
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 8
            assert TlsQualysScan.objects.filter(qualys_rating="B").count() == 2
            assert TlsQualysScan.objects.filter(qualys_rating="C").count() == 0

    announce_testcase(6, "Simulate the entire process of finding and resolving a domain.")
    Counter().reset()
    with freeze_time('2000-1-9', tick=True, tz_offset=1):
        with HTTMock(qualys_realistic_scan):
            tls_qualys.compose_manual_scan_task()(urls_filter={'name__in': ["www.faalkaart.nl"]})

            # no update on the rating, so no new scans.
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 8
            # todo: the date of the scan should be updated.
            # todo: there is no way to assert if we have gotten intermediate responses

    announce_testcase(7, "Simulate an erroneous domain: it should not be added.")
    Counter().reset()
    with freeze_time('2000-1-11', tick=True, tz_offset=1):
        with HTTMock(qualys_error_scan):
            tls_qualys.compose_manual_scan_task()(urls_filter={'name__in': ["www.faalkaart.nl"]})

            # no update on the rating, so no new scan.
            # the endpoints should now be set to dead...
            assert TlsQualysScan.objects.filter(qualys_rating="A").count() == 8

    # announce_testcase(8, "Simulate a domain that just doesn't get out of the DNS phase.")

    # todo: add a scan that has has not yet finished
    # todo: check if the endpoints are set to pending when a scan has been requested.

    # we kunnen nog kijken of iets een domain is. en of qualys dat mirrort.
