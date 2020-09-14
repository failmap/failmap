from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.tls_qualys import save_scan
from websecmap.scanners.tests.test_plannedscan import create_url


def test_qualys_save_data(db):
    """
    Situation where the ipv4 and ipv6 endpoints exist, but the ipv4 endpoint is not recognized by qualys.
    The ipv4 and ipv6 endpoints are validated to be existing with scanner http, and they actually really do exist.
    In this situation the ipv4 scan might have been blocked by a firewall, but the ipv6 scan isn't. For example.

    Should store scan errors.
    """

    data = {
        "host": "werkplek.alkmaar.nl",
        "port": 443,
        "protocol": "http",
        "isPublic": True,
        "status": "READY",
        "startTime": 1597216890988,
        "testTime": 1597217025442,
        "engineVersion": "2.1.5",
        "criteriaVersion": "2009q",
        "endpoints": [
            {
                "ipAddress": "2a02:2738:1:1:0:0:0:67",
                "serverName": "nsx01.alkmaar.nl",
                "statusMessage": "Ready",
                "grade": "B",
                "gradeTrustIgnored": "B",
                "hasWarnings": False,
                "isExceptional": False,
                "progress": 100,
                "duration": 118567,
                "eta": 12,
                "delegation": 1,
                "details": {},
            },
            {
                "ipAddress": "93.93.121.103",
                "serverName": "nsx01.alkmaar.nl",
                "statusMessage": "Unable to connect to the server",
                "statusDetails": "TESTING_PROTO_2_0",
                "statusDetailsMessage": "Testing SSL 2.0",
                "progress": -1,
                "duration": 15022,
                "eta": -1,
                "delegation": 1,
                "details": {},
            },
        ],
    }

    u = create_url("werkplek.alkmaar.nl")

    save_scan(u, data)

    # force created two endpoints
    assert Endpoint.objects.all().count() == 2

    # with both a scan for tls_qualys_encryption_quality and tls_qualys_certificate_trusted
    assert EndpointGenericScan.objects.all().count() == 4

    # of which one is a B, and the other is a "scan_error"
    scan_results = []
    for scan in EndpointGenericScan.objects.all():
        scan_results.append(scan.rating)

    assert sorted(scan_results) == sorted(["B", "trusted", "scan_error", "scan_error"])
