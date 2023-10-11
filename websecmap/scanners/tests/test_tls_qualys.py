from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.tls_qualys import save_scan, get_certs
from websecmap.scanners.tests.test_plannedscan import create_url
import json


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

    save_scan(u.url, data)

    # force created two endpoints
    assert Endpoint.objects.all().count() == 2

    # with both a scan for tls_qualys_encryption_quality and tls_qualys_certificate_trusted
    assert EndpointGenericScan.objects.all().count() == 4

    # of which one is a B, and the other is a "scan_error"
    scan_results = []
    for scan in EndpointGenericScan.objects.all():
        scan_results.append(scan.rating)

    assert sorted(scan_results) == sorted(["B", "trusted", "scan_error", "scan_error"])


def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)


def test_get_certs(current_path):
    data = load_json(f"{current_path}/websecmap/scanners/tests/tls_qualys/scanresult_normal.json")

    # there are two ipv4 results but the certificates are the same, so don't bother getting both.
    certs = get_certs(data, 4)
    assert certs == [
        {
            "subject": "CN=www.arnhem.nl, O=Gemeente Arnhem, L=Arnhem, ST=Gelderland, C=NL",
            "commonNames": ["www.arnhem.nl"],
            "altNames": [
                "www.arnhem.nl",
                "7pm.nl",
                "afvalwijzerarnhem.nl",
                "arnhem.nl",
                "arnhemstemt.nl",
                "arnhemtrouwt.nl",
                "mijn.arnhem.nl",
                "raad.arnhem.nl",
                "rekenkamerarnhem.nl",
                "www.7pm.nl",
            ],
            "notBefore": 1683903426000,
            "notAfter": 1715525520000,
            "issuerSubject": "CN=QuoVadis Global SSL ICA G2, O=QuoVadis Limited, C=BM",
            "issuerLabel": "QuoVadis Global SSL ICA G2",
            "sigAlg": "SHA256withRSA",
            "revocationInfo": 3,
            "crlURIs": ["http://crl.quovadisglobal.com/qvsslg2.crl"],
            "ocspURIs": ["http://ocsp.quovadisglobal.com"],
            "revocationStatus": 2,
            "crlRevocationStatus": 2,
            "ocspRevocationStatus": 2,
            "sgc": 0,
            "issues": 0,
            "sct": True,
            "mustStaple": 0,
            "sha1Hash": "119563476e4220aaedfaaeea76a6667bd6012b7c",
            "pinSha256": "GLz1D57+h2GR+JCwb5WJ7KdFQ6BNIFiEAM5eCjbQjbY=",
        }
    ]

    # v6 has two unique certs for some reason (misconfiguration)
    certs = get_certs(data, 6)
    assert certs == [
        {
            "subject": "CN=www.arnhem.nl, O=Gemeente Arnhem, L=Arnhem, ST=Gelderland, C=NL",
            "commonNames": ["www.arnhem.nl"],
            "altNames": [
                "www.arnhem.nl",
                "7pm.nl",
                "afvalwijzerarnhem.nl",
                "arnhem.nl",
                "arnhemstemt.nl",
                "arnhemtrouwt.nl",
                "mijn.arnhem.nl",
                "raad.arnhem.nl",
                "rekenkamerarnhem.nl",
                "www.7pm.nl",
            ],
            "notBefore": 1683903426000,
            "notAfter": 1715525520000,
            "issuerSubject": "CN=QuoVadis Global SSL ICA G2, O=QuoVadis Limited, C=BM",
            "issuerLabel": "QuoVadis Global SSL ICA G2",
            "sigAlg": "SHA256withRSA",
            "revocationInfo": 3,
            "crlURIs": ["http://crl.quovadisglobal.com/qvsslg2.crl"],
            "ocspURIs": ["http://ocsp.quovadisglobal.com"],
            "revocationStatus": 2,
            "crlRevocationStatus": 2,
            "ocspRevocationStatus": 2,
            "sgc": 0,
            "issues": 0,
            "sct": True,
            "mustStaple": 0,
            "sha1Hash": "119563476e4220aaedfaaeea76a6667bd6012b7c",
            "pinSha256": "GLz1D57+h2GR+JCwb5WJ7KdFQ6BNIFiEAM5eCjbQjbY=",
        },
        {
            "subject": "CN=www.arnhem.nl, O=Gemeente Arnhem, L=Arnhem, ST=Gelderland, C=NL",
            "commonNames": ["www.arnhem.nl"],
            "altNames": [
                "www.arnhem.nl",
                "7pm.nl",
                "afvalwijzerarnhem.nl",
                "arnhem.nl",
                "arnhemstemt.nl",
                "arnhemtrouwt.nl",
                "mijn.arnhem.nl",
                "raad.arnhem.nl",
                "rekenkamerarnhem.nl",
                "www.7pm.nl",
            ],
            "notBefore": 1683903426000,
            "notAfter": 1715525520000,
            "issuerSubject": "CN=QuoVadis Global SSL ICA G2, O=QuoVadis Limited, C=BM",
            "issuerLabel": "QuoVadis Global SSL ICA G2",
            "sigAlg": "SHA256withRSA",
            "revocationInfo": 3,
            "crlURIs": ["http://crl.quovadisglobal.com/qvsslg2.crl"],
            "ocspURIs": ["http://ocsp.quovadisglobal.com"],
            "revocationStatus": 2,
            "crlRevocationStatus": 2,
            "ocspRevocationStatus": 2,
            "sgc": 0,
            "issues": 0,
            "sct": True,
            "mustStaple": 0,
            "sha1Hash": "229563476e4220aaedfaaeea76a6667bd6012b7c",
            "pinSha256": "GLz1D57+h2GR+JCwb5WJ7KdFQ6BNIFiEAM5eCjbQjbY=",
        },
    ]
