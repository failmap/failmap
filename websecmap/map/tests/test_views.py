from datetime import datetime

import pytz

from websecmap.map.logic.stats_and_graphs import what_to_improve
from websecmap.map.views import config_content
from websecmap.organizations.models import Url, OrganizationType, Organization
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan


def test_config(db):
    conf = config_content()
    assert conf["project"]["country"] == "NL"
    assert conf["debug"] is False
    assert conf["show"]["issues"]["http_security_header_x_xss_protection"] is True


def setup():
    now = datetime.now(pytz.utc)
    ott = OrganizationType(**{'name': 'gov'})
    ott.save()
    url = Url(**{"url": "example.com"})
    url.save()
    org = Organization(**{'name': 'Texel', 'country': 'NL', 'type': ott})
    org.save()
    org.add_url('example.com')
    endp = Endpoint(**{'url': url})
    endp.save()
    scan = EndpointGenericScan(**{'endpoint': endp, 'rating': 'failed', 'type': 'internet_nl_web_ipv6_ws_address', 'rating_determined_on': now})
    scan.save()
    scan = EndpointGenericScan(**{'endpoint': endp, 'rating': 'passed', 'type': 'internet_nl_web_ipv6_ws_address', 'rating_determined_on': now})
    scan.save()
    scan = EndpointGenericScan(**{'endpoint': endp, 'rating': 'passed', 'type': 'internet_nl_web_ipv6_ns_address', 'rating_determined_on': now})
    scan.save()
    scan = UrlGenericScan(**{'url': url, 'rating': 'error', 'type': 'dnssec', 'rating_determined_on': now})
    scan.save()

    ScanPolicy(**{'scan_type': 'internet_nl_web_ipv6_ws_address', 'conclusion': 'failed', 'high': 1}).save()
    ScanPolicy(**{'scan_type': 'dnssec', 'conclusion': 'error', 'high': 1}).save()


def test_what_to_improve(db):
    # Add two tests to the db, one that needs to be improved, and one that doesn't.
    # The view should show 1 thing... for both endpoint and url
    # It seems you get the 'municipality' type for free?
    # assert OrganizationType.objects.all().count() == 0
    setup()
    # assert OrganizationType.objects.all().count() == 1

    output = what_to_improve("NL", "gov", "internet_nl_web_ipv6_ws_address")
    assert output == [{}]

    # And for urls
    output = what_to_improve("NL", "gov", "dnssec")
    assert output == [{}]

