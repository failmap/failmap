from websecmap.scanners.export_metrics import (
    pivot_location_evidence,
    pivot_cookies,
    pivot_cookie_locations,
    pivot_products,
    pivot_cookie_meaning,
)


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
        },
    ]
