from datetime import datetime, timezone

from websecmap.map.logic.stats_and_graphs import what_to_improve
from websecmap.map.views import config_content
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan


def test_config(db, default_scan_metadata):
    run_setup()
    conf = config_content()
    assert conf["project"]["country"] == "NL"
    assert conf["debug"] is False
    assert conf["show"]["issues"]["http_security_header_x_xss_protection"] is True


now = datetime.now(timezone.utc)


def run_setup():
    # Automagically called, but not with the database fixture, so this has been renamed to run_setup
    ott = OrganizationType(**{"name": "gov"})
    ott.save()
    url = Url(**{"url": "example.com"})
    url.save()
    org = Organization(**{"name": "Texel", "country": "NL", "type": ott})
    org.save()
    org.layers.add(ott)

    org.add_url("example.com")
    endp = Endpoint(**{"url": url})
    endp.save()
    scan = EndpointGenericScan(
        **{
            "endpoint": endp,
            "rating": "failed",
            "type": "internet_nl_web_ipv6_ws_address",
            "rating_determined_on": now,
            "is_the_latest_scan": True,
        }
    )
    scan.save()
    scan = EndpointGenericScan(
        **{
            "endpoint": endp,
            "rating": "passed",
            "type": "internet_nl_web_ipv6_ws_address",
            "rating_determined_on": now,
            "is_the_latest_scan": False,
        }
    )
    scan.save()
    scan = EndpointGenericScan(
        **{
            "endpoint": endp,
            "rating": "passed",
            "type": "internet_nl_web_ipv6_ns_address",
            "rating_determined_on": now,
            "is_the_latest_scan": True,
        }
    )
    scan.save()
    scan = UrlGenericScan(
        **{"url": url, "rating": "error", "type": "dnssec", "rating_determined_on": now, "is_the_latest_scan": True}
    )
    scan.save()

    ScanPolicy(**{"scan_type": "internet_nl_web_ipv6_ws_address", "conclusion": "failed", "high": 1}).save()
    ScanPolicy(**{"scan_type": "dnssec", "conclusion": "error", "high": 1}).save()


def test_what_to_improve(db, default_scan_metadata):
    run_setup()
    # Add two tests to the db, one that needs to be improved, and one that doesn't.
    # The view should show 1 thing... for both endpoint and url

    output = what_to_improve("NL", "gov", "internet_nl_web_ipv6_ws_address")
    output[0]["last_scan_moment"] = None
    assert output == [
        {
            "domain": "example.com",
            "rating_determined_on": now,
            "last_scan_moment": None,
            "severity": "high",
            "subdomain": "",
            "url_url": "example.com",
        },
    ]

    # And for urls
    output = what_to_improve("NL", "gov", "dnssec")
    output[0]["last_scan_moment"] = None
    assert output == [
        {
            "domain": "example.com",
            "last_scan_moment": None,
            "rating_determined_on": now,
            "severity": "high",
            "subdomain": "",
            "url_url": "example.com",
        },
    ]
