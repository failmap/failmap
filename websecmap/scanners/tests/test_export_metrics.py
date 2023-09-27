from websecmap.scanners.export_metrics import pivot_location_evidence, pivot_cookies, pivot_cookie_locations


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
            "rating": "location_medium",
            "continent_code": "NA",
            "country_iso_code": "US",
            "city_in_en": "Kansas City",
            "as_number": 396982,
            "as_organization": "GOOGLE-CLOUD-PLATFORM",
            "isp_ame": "Google Cloud",
            "network": "34.98.64.0/18",
            "country_rating": "medium",
            "continent_rating": "medium",
            "priority": "",
            "domain": "app-script.monsido.com",
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


def test_pivot_cookie_locations():
    # note the 2 in cookie number 2, expecting two records, one for each cookie with the same location data...
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
            "as_number": 43366,
            "as_organization": "OSSO B.V.",
            "city_in_en": "",
            "continent_code": "EU",
            "continent_rating": "ok",
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
            "country_iso_code": "NL",
            "country_rating": "unknown",
            "domain": "intranet-acc.landvancuijk.nl",
            "isp_ame": "OSSO B.V.",
            "network": "195.28.22.0/23",
            "priority": "",
            "rating": "location_ok",
        },
        {
            "as_number": 43366,
            "as_organization": "OSSO B.V.",
            "city_in_en": "",
            "continent_code": "EU",
            "continent_rating": "ok",
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
            "country_iso_code": "NL",
            "country_rating": "unknown",
            "domain": "intranet-acc.landvancuijk.nl",
            "isp_ame": "OSSO B.V.",
            "network": "195.28.22.0/23",
            "priority": "",
            "rating": "location_ok",
        },
    ]
