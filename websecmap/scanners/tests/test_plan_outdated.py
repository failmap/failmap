from datetime import datetime, timedelta

import pytz

from websecmap.map.models import Configuration, OrganizationReport
from websecmap.organizations.models import OrganizationType
from websecmap.scanners.models import PlannedScan
from websecmap.scanners.plannedscan import plan_outdated_scans
from websecmap.scanners.tests.test_plannedscan import (create_organization, create_url,
                                                       link_url_to_organization)


def test_plan_outdated_scans(db):
    o = create_organization("Test")
    u1 = create_url("example.com")
    link_url_to_organization(u1, o)
    u2 = create_url("example2.com")
    link_url_to_organization(u2, o)

    # make sure there is a map configuration, as outdated can only happen for things that are reported / displayed
    # on a map.
    ot = OrganizationType()
    ot.name = "Test"
    ot.save()

    o.country = "NL"
    o.type = ot
    o.save()

    m = Configuration()
    m.country = "NL"
    m.organization_type = ot
    m.is_scanned = True
    m.is_displayed = True
    m.is_reported = True
    m.save()

    example_report = {
        "organization": {
            "urls": [
                {
                    "url": "example.com",
                    "ratings": [],
                    "endpoints": [
                        {
                            "ratings": [
                                {"type": "http_security_header_strict_transport_security",
                                 "since": "2010-08-05T18:57:53.873815+00:00",
                                 "last_scan": "2010-08-07T14:34:56.917953+00:00",
                                 "scan_type": "http_security_header_strict_transport_security"},
                                {"type": "http_security_header_x_frame_options",
                                 "since": "2010-08-05T18:57:53.856580+00:00",
                                 "last_scan": "2010-08-07T14:34:56.898717+00:00",
                                 "scan_type": "http_security_header_x_frame_options"},
                                {"type": "http_security_header_x_content_type_options",
                                 "since": "2010-08-05T18:57:53.864561+00:00",
                                 "last_scan": "2010-08-07T14:34:56.907224+00:00",
                                 "scan_type": "http_security_header_x_content_type_options"},
                                {"type": "http_security_header_x_xss_protection",
                                 "since": "2020-08-05T18:57:53.845210+00:00",
                                 "last_scan": "2020-08-07T14:34:56.881692+00:00",
                                 "scan_type": "http_security_header_x_xss_protection"}],
                        }
                    ],
                }
            ],
        }
    }
    r = OrganizationReport()
    r.calculation = example_report
    r.organization = o
    r.at_when = datetime.now(pytz.utc) - timedelta(days=100)
    r.save()

    assert len(r.calculation['organization']) == 1

    assert PlannedScan.objects.all().count() == 0

    published_scan_types = ['http_security_header_strict_transport_security',
                            'http_security_header_x_content_type_options']
    plan_outdated_scans(published_scan_types)

    """
    Expected:

    [{'activity': 'scan', 'scanner': 'security_headers', 'url': 'example.com'},
     {'activity': 'discover', 'scanner': 'http', 'url': 'example.com'},
     {'activity': 'verify', 'scanner': 'http', 'url': 'example.com'}]

    As both scans originate from the same scanner, and have the same underlaying scanner.
    """
    assert PlannedScan.objects.all().count() == 3
