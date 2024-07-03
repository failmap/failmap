from datetime import timezone, datetime
from typing import Tuple

import copy
import pyexcel
from django.core.management import call_command
from freezegun import freeze_time

from websecmap.organizations.models import Url, Organization, OrganizationType
from websecmap.scanners.export_metrics import (
    pivot_location_evidence,
    pivot_cookies,
    pivot_cookie_locations,
    pivot_products,
    pivot_cookie_meaning,
    create_pivot_data,
    parse_issuer_subject,
)
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_pivot_location_evidence():
    input = [
        {
            "rating": "location_medium",
            "evidence": {
                "found_location": {
                    "continent_code": "NA",
                    "country_iso_code": "US",
                    "city_in_en": "Kansas City",
                    "as_number": 396982,
                    "as_organization": "GOOGLE-CLOUD-PLATFORM",
                    "isp_ame": "Google Cloud",
                    "network": "34.98.64.0/18",
                },
                "country_rating": "medium",
                "continent_rating": "medium",
            },
            "domain": "app-script.monsido.com",
        }
    ]
    output = pivot_location_evidence(input)
    assert output == [
        {
            "location_rating": "location_medium",
            "location_continent_code": "NA",
            "location_country_iso_code": "US",
            "location_city_in_en": "Kansas City",
            "location_as_number": 396982,
            "location_as_organization": "GOOGLE-CLOUD-PLATFORM",
            "location_isp_ame": "Google Cloud",
            "location_network": "34.98.64.0/18",
            "location_country_rating": "medium",
            "location_continent_rating": "medium",
            "location_priority": "",
            "location_domain": "app-script.monsido.com",
        }
    ]


def test_pivot_cookies():
    input = [
        {
            "name": "ClientId",
            "domain": "outlook.office365.com",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
        }
    ]

    output = pivot_cookies(input)

    assert output == [
        {
            "cookie_name": "ClientId",
            "cookie_domain": "outlook.office365.com",
            "cookie_path": "/",
            "cookie_httpOnly": False,
            "cookie_secure": True,
            "cookie_sameSite": "None",
            "cookie_name_normalized": "ClientId",
            "cookie_parsed_domain": "office365",
            "cookie_parsed_domainsuffix": "com",
            "cookie_parsed_fqdn": "outlook.office365.com",
            "cookie_parsed_subdomain": "outlook",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
    ]


def test_pivot_products():
    # only the product keys are taken.
    input = [
        {
            "product_id": 274,
            "product_name": "ASP.NET",
            "product_version": "unknown",
            "product_vendor_name": "Microsoft",
            "product_vendor_id": "1",
            "random_other_data": "something",
        },
        {
            "product_id": 2,
            "product_name": "ASP.NET2",
            "product_version": "1",
            "product_vendor_name": "Microsoft",
            "product_vendor_id": "1",
        },
    ]

    output = pivot_products(input)

    assert output == [
        {
            "product_id": 274,
            "product_name": "ASP.NET",
            "product_version": "unknown",
            "product_vendor_name": "Microsoft",
            "product_vendor_id": "1",
        },
        {
            "product_id": 2,
            "product_name": "ASP.NET2",
            "product_version": "1",
            "product_vendor_name": "Microsoft",
            "product_vendor_id": "1",
        },
    ]


def test_pivot_cookie_locations():
    # note the 2 in cookie number 2, expecting two records, one for each cookie with the same location data...
    # This works as a domain has 1 location at some time.
    # This currently also works because is just one product. The product hierarchy is not taken into account rn.
    input = [
        {
            "rating": "location_ok",
            "evidence": {
                "found_location": {
                    "continent_code": "EU",
                    "country_iso_code": "NL",
                    "city_in_en": "",
                    "as_number": 43366,
                    "as_organization": "OSSO B.V.",
                    "isp_ame": "OSSO B.V.",
                    "network": "195.28.22.0/23",
                },
                "country_rating": "unknown",
                "continent_rating": "ok",
            },
            "domain": "intranet-acc.landvancuijk.nl",
            "applicable_cookies": [
                {
                    "name": "OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
                    "domain": "intranet-acc.landvancuijk.nl",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None",
                },
                {
                    "name": "2_OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
                    "domain": "intranet-acc.landvancuijk.nl",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None",
                },
            ],
        }
    ]

    output = pivot_cookie_locations(input)
    assert output == [
        {
            "cookie_domain": "intranet-acc.landvancuijk.nl",
            "cookie_httpOnly": True,
            "cookie_name": "OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
            "cookie_name_normalized": "OpenIdConnect.nonce.<HASH_OR_ID>",
            "cookie_parsed_domain": "landvancuijk",
            "cookie_parsed_domainsuffix": "nl",
            "cookie_parsed_fqdn": "intranet-acc.landvancuijk.nl",
            "cookie_parsed_subdomain": "intranet-acc",
            "cookie_path": "/",
            "cookie_sameSite": "None",
            "cookie_secure": True,
            "location_as_number": 43366,
            "location_as_organization": "OSSO B.V.",
            "location_city_in_en": "",
            "location_continent_code": "EU",
            "location_continent_rating": "ok",
            "location_country_iso_code": "NL",
            "location_country_rating": "unknown",
            "location_domain": "intranet-acc.landvancuijk.nl",
            "location_isp_ame": "OSSO B.V.",
            "location_network": "195.28.22.0/23",
            "location_priority": "",
            "location_rating": "location_ok",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
        {
            "cookie_domain": "intranet-acc.landvancuijk.nl",
            "cookie_httpOnly": True,
            "cookie_name": "2_OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
            "cookie_name_normalized": "2_OpenIdConnect.nonce.vOur6PVRCBGfx8IXbV%2FVi3iEM83xsoymaqEYvgC5%2BTg%3D",
            "cookie_parsed_domain": "landvancuijk",
            "cookie_parsed_domainsuffix": "nl",
            "cookie_parsed_fqdn": "intranet-acc.landvancuijk.nl",
            "cookie_parsed_subdomain": "intranet-acc",
            "cookie_path": "/",
            "cookie_sameSite": "None",
            "cookie_secure": True,
            "location_as_number": 43366,
            "location_as_organization": "OSSO B.V.",
            "location_city_in_en": "",
            "location_continent_code": "EU",
            "location_continent_rating": "ok",
            "location_country_iso_code": "NL",
            "location_country_rating": "unknown",
            "location_domain": "intranet-acc.landvancuijk.nl",
            "location_isp_ame": "OSSO B.V.",
            "location_network": "195.28.22.0/23",
            "location_priority": "",
            "location_rating": "location_ok",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
    ]


def test_pivot_cookie_meaning():
    #
    meaning_input = {
        "products": [
            {
                "cookies": [
                    {"name": "ARRAffinity", "domain": ".example.com", "path": "/"},
                    {"name": "ARRAffinitySameSite", "domain": ".example.com", "path": "/"},
                ],
                "product_id": 274,
                "product_name": "ASP.NET",
                "product_version": "unknown",
                "product_vendor_name": "Microsoft",
                "product_vendor_id": 0,
            }
        ],
        "locations": [
            {
                "rating": "location_ok",
                "evidence": {
                    "found_location": {
                        "continent_code": "EU",
                        "country_iso_code": "NL",
                        "city_in_en": "Aerdenhout",
                        "as_number": 41887,
                        "as_organization": "Prolocation B.V.",
                        "isp_ame": "Prolocation BV",
                        "network": "178.22.84.0/23",
                    },
                    "country_rating": "unknown",
                    "continent_rating": "ok",
                },
                "domain": "www.rijksoverheid.nl",
                "applicable_cookies": [{"name": "ARRAffinitySameSite", "domain": ".example.com", "path": "/"}],
            }
        ],
        "locations_worst_rating": "location_ok",
    }

    # evidence is used to make sure there is a 100% coverage. Cookies are checked inside location and products and
    # select the right one of each.
    evidence_input = [
        {
            "name": "ARRAffinity",
            "domain": ".example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "ARRAffinitySameSite",
            "domain": ".example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        },
        {
            "name": "NoLocationNoProduct",
            "domain": ".proc.live",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        },
    ]

    output = pivot_cookie_meaning(evidence_input, meaning_input)

    assert output == [
        {
            "cookie_domain": ".example.com",
            "cookie_httpOnly": True,
            "cookie_name": "ARRAffinity",
            "cookie_name_normalized": "ARRAffinity",
            "cookie_parsed_domain": "example",
            "cookie_parsed_domainsuffix": "com",
            "cookie_parsed_fqdn": "example.com",
            "cookie_parsed_subdomain": "",
            "cookie_path": "/",
            "cookie_sameSite": "Lax",
            "cookie_secure": True,
            "location_as_number": -1,
            "location_as_organization": "",
            "location_city_in_en": "",
            "location_continent_code": "",
            "location_continent_rating": "",
            "location_country_iso_code": "",
            "location_country_rating": "",
            "location_domain": "",
            "location_isp_ame": "",
            "location_network": "",
            "location_priority": "",
            "location_rating": None,
            "product_id": 274,
            "product_name": "ASP.NET",
            "product_vendor_id": 0,
            "product_vendor_name": "Microsoft",
            "product_version": "unknown",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
        {
            "cookie_domain": ".example.com",
            "cookie_httpOnly": True,
            "cookie_name": "ARRAffinitySameSite",
            "cookie_name_normalized": "ARRAffinitySameSite",
            "cookie_parsed_domain": "example",
            "cookie_parsed_domainsuffix": "com",
            "cookie_parsed_fqdn": "example.com",
            "cookie_parsed_subdomain": "",
            "cookie_path": "/",
            "cookie_sameSite": "None",
            "cookie_secure": True,
            "location_as_number": 41887,
            "location_as_organization": "Prolocation B.V.",
            "location_city_in_en": "Aerdenhout",
            "location_continent_code": "EU",
            "location_continent_rating": "ok",
            "location_country_iso_code": "NL",
            "location_country_rating": "unknown",
            "location_domain": "www.rijksoverheid.nl",
            "location_isp_ame": "Prolocation BV",
            "location_network": "178.22.84.0/23",
            "location_priority": "",
            "location_rating": "location_ok",
            "product_id": 274,
            "product_name": "ASP.NET",
            "product_vendor_id": 0,
            "product_vendor_name": "Microsoft",
            "product_version": "unknown",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
        {
            "cookie_domain": ".proc.live",
            "cookie_httpOnly": True,
            "cookie_name": "NoLocationNoProduct",
            "cookie_name_normalized": "NoLocationNoProduct",
            "cookie_parsed_domain": "proc",
            "cookie_parsed_domainsuffix": "live",
            "cookie_parsed_fqdn": "proc.live",
            "cookie_parsed_subdomain": "",
            "cookie_path": "/",
            "cookie_sameSite": "None",
            "cookie_secure": True,
            "location_as_number": -1,
            "location_as_organization": "",
            "location_city_in_en": "",
            "location_continent_code": "",
            "location_continent_rating": "",
            "location_country_iso_code": "",
            "location_country_rating": "",
            "location_domain": "",
            "location_isp_ame": "",
            "location_network": "",
            "location_priority": "",
            "location_rating": None,
            "product_id": 0,
            "product_name": "",
            "product_vendor_id": 0,
            "product_vendor_name": "",
            "product_version": "",
            "cookie_indicator": 0,
            "cookie_purpose": "",
            "cookie_purpose_rating": "",
        },
    ]


def test_create_pivot_data(db, current_path):
    # nothing exists and nothing should be returned, no crashes
    data = create_pivot_data(scan_types=[], layers=[])
    assert data == []
    data = create_pivot_data(scan_types=["scan_type_1", "scan_type_2"], layers=["municipality", "test"])
    assert data == []

    # create two of everything to test a mix and match of everything.
    with freeze_time("2020-01-01"):
        lay1, org1, url1, eps1, scan1 = create_test_dataset("layer_1", "organization_name", "url_1.nl", "scan_type_1")
        lay2, org2, url2, eps2, scan2 = create_test_dataset("layer_2", "org_2", "url_2.nl", "scan_type_2")
    data = create_pivot_data(scan_types=["scan_type_1", "scan_type_2"], layers=["layer_1", "layer_2"])

    # default 1 is just a placeholder metric which makes for easy summing of a result
    assert len(data) == 2
    expected_1 = [
        {
            "computed_domain": "url_1",
            "computed_subdomain": "",
            "computed_suffix": "nl",
            "default": 1,
            "endpoint_ip_version": 4,
            "endpoint_port": 80,
            "endpoint_protocol": "http",
            "is_explained": False,
            "layer": "layer_1",
            "organization_country": "",
            "organization_id": org1.id,
            "organization_name": "organization_name",
            "scan_rating": "0",
            "scan_rating_determined_on": "2020-01-01T00:00:00+00:00",
            "scan_last_scan_moment": "2020-01-01T00:00:00+00:00",
            "scan_type": "scan_type_1",
            "url": "url_1.nl",
        },
    ]
    expected_2 = [
        {
            "computed_domain": "url_2",
            "computed_subdomain": "",
            "computed_suffix": "nl",
            "default": 1,
            "endpoint_ip_version": 4,
            "endpoint_port": 80,
            "endpoint_protocol": "http",
            "is_explained": False,
            "layer": "layer_2",
            "organization_country": "",
            "organization_id": org2.id,
            "organization_name": "org_2",
            "scan_rating": "0",
            "scan_rating_determined_on": "2020-01-01T00:00:00+00:00",
            "scan_last_scan_moment": "2020-01-01T00:00:00+00:00",
            "scan_type": "scan_type_2",
            "url": "url_2.nl",
        },
    ]
    assert data == expected_1 + expected_2

    # and just for one layer
    data = create_pivot_data(scan_types=["scan_type_1"], layers=["layer_1"])
    assert data == expected_1

    # call the command and see that it also returned correctly
    # read the data with a spreadsheet reader and see if there is only one record
    filename = call_command("export_pivot", "scan_type_1", "layer_1")
    exported_file = f"{current_path}/websecmap/uploads/{filename}"
    book = pyexcel.get_dict(file_name=exported_file)
    assert dict(book) == {
        "computed_domain": ["url_1"],
        "computed_subdomain": [""],
        "computed_suffix": ["nl"],
        "default": [1],
        "endpoint_ip_version": [4],
        "endpoint_port": [80],
        "endpoint_protocol": ["http"],
        "is_explained": [False],
        "layer": ["layer_1"],
        "organization_country": [""],
        "organization_id": [org1.id],
        "organization_name": ["organization_name"],
        "scan_rating": ["0"],
        "scan_rating_determined_on": ["2020-01-01T00:00:00+00:00"],
        "scan_last_scan_moment": ["2020-01-01T00:00:00+00:00"],
        "scan_type": ["scan_type_1"],
        "url": ["url_1.nl"],
    }

    # cross reference some stuff to see that these references are not exported (aka: from another layer)
    # Org 2 is now also in layer 1, so will be exported with an export of layer 1
    # but the metric is not called for in the next call, so it will not export anything for org 2
    org2.layers.add(lay1)
    url2.organization.add(org2)
    data = create_pivot_data(scan_types=["scan_type_1"], layers=["layer_1"])
    assert data == expected_1

    expected_3 = copy.deepcopy(expected_2)
    expected_3[0]["layer"] = "layer_1"

    # org 2 has been added to layer 1 and that means scan type 2 is findable on layer 1
    data = create_pivot_data(scan_types=["scan_type_1", "scan_type_2"], layers=["layer_1"])
    assert data == expected_1 + expected_3

    # retrieving layer 2 should never yield a layer 1. Even if organization 2 is in layer 1.
    data = create_pivot_data(scan_types=["scan_type_2"], layers=["layer_2"])
    assert data == expected_2


def create_test_dataset(
    layer_name, organization_name, url, scan_type_name
) -> Tuple[OrganizationType, Organization, Url, Endpoint, EndpointGenericScan]:
    # Two scans in two different layers of different types, they should be filterable on layer and type
    layer_1 = OrganizationType.objects.create(name=layer_name)
    org_1 = Organization.objects.create(name=organization_name)
    org_1.layers.add(layer_1)
    url_1 = Url.objects.create(url=url)
    url_1.organization.add(org_1)
    ep_1 = Endpoint.objects.create(url=url_1, port=80, protocol="http")
    kwargs_1 = {"endpoint": ep_1, "rating_determined_on": datetime.now(timezone.utc)}
    scan_1 = EndpointGenericScan.objects.create(type=scan_type_name, is_the_latest_scan=True, **kwargs_1)

    return layer_1, org_1, url_1, ep_1, scan_1


def test_parse_issuer_subject():
    data = parse_issuer_subject("")
    assert data == {
        "C": "",
        "O": "",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    data = parse_issuer_subject("CN=Microsoft Azure RSA TLS Issuing CA 07, O=Microsoft Corporation, C=US")
    assert data == {
        "C": "US",
        "O": "Microsoft Corporation",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "Microsoft Azure RSA TLS Issuing CA 07",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    # extra fields such as EMAILADDRESS are not returned
    data = parse_issuer_subject(
        "EMAILADDRESS=root@domain.nl, CN=sdomain.nl, OU=SomeOrganizationalUnit, " "O=org, L=city, ST=state, C=--"
    )
    assert data == {
        "C": "--",
        "O": "org",
        "OU": "SomeOrganizationalUnit",
        "Q": "",
        "ST": "state",
        "L": "city",
        "CN": "sdomain.nl",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    data = parse_issuer_subject("CN=DigiCert G2 TLS EU RSA4096 SHA384 2022 CA1, O=DigiCert Ireland Limited, C=IE")
    assert data == {
        "C": "IE",
        "O": "DigiCert Ireland Limited",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "DigiCert G2 TLS EU RSA4096 SHA384 2022 CA1",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    data = parse_issuer_subject("CN=TRAEFIK DEFAULT CERT")
    assert data == {
        "C": "",
        "O": "",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "TRAEFIK DEFAULT CERT",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    data = parse_issuer_subject("CN=Kubernetes Ingress Controller Fake Certificate, O=Acme Co")
    assert data == {
        "C": "",
        "O": "Acme Co",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "Kubernetes Ingress Controller Fake Certificate",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }

    data = parse_issuer_subject("CN=GTS CA 1D4, O=Google Trust Services LLC, C=US")
    assert data == {
        "C": "US",
        "O": "Google Trust Services LLC",
        "OU": "",
        "Q": "",
        "ST": "",
        "L": "",
        "CN": "GTS CA 1D4",
        "businessCategory": "",
        "SERIALNUMBER": "",
    }
