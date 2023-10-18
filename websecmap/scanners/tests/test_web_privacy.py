from datetime import datetime, timezone

import pytest
from deepdiff import DeepDiff
from constance.test import override_config

from websecmap.organizations.models import Url
from websecmap.scanners.models import (
    Endpoint,
    EndpointGenericScan,
    ProductCookieIndicator,
    Product,
    ProductVendor,
    CookiePurpose,
)
from websecmap.scanners.scanner.web_privacy import (
    store,
    scan,
    truncate_long_post_data,
    remove_duplicate_third_party_requests,
    product_meaning_from_cookies,
    strip_irrelevant_cookie_fields,
    update_meaning_of_location_and_products_at_web_privacy_cookies,
    worse_rating,
)

from websecmap.scanners.scanner.web_privacy_resources.trackers import (
    get_known_trackers_from_urls,
    get_tracker_info_from_disconnectme,
)

from .test_location import create_sample_domainip, create_sample_geoip
from ..scanner.metric_constants import (
    WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_HIGH,
    WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM,
    WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_OK,
)


def test_get_tracker_info():
    # Just an url would not return anything
    assert get_tracker_info_from_disconnectme("example.com") == {}

    # See if we can match domains to known trackers from disconnectme...
    assert get_tracker_info_from_disconnectme("bitrix24.com") == {
        "Category": "EmailAggressive",
        "Company": "Bitrix24",
        "Platform": "https://www.bitrix24.com/",
        "Tracking Url": "bitrix24.com",
    }

    assert get_tracker_info_from_disconnectme("mkt10008.com") == {
        "Category": "EmailAggressive",
        "Company": "Acoustic",
        "Platform": "https://www.acoustic.com/",
        "Tracking Url": "mkt10008.com",
    }


def demo_data():
    return {
        "third-party-requests-structured": [
            {
                "url": "https://script.shoppingminds.com/rvo_nl/index.js?_=1687874430050",
                "resource_type": "script",
                "method": "GET",
                "post_data": None,
            },
            {
                "url": "https://trkr.shoppingminds.net/api/rvo/rvo",
                "resource_type": "xhr",
                "method": "POST",
                "post_data": "siteInfo%5Bsite%5D=rvo&siteInfo%5Blanguage%5D=nl&siteInfo%5Bcountry%5D=nl&action=ne",
            },
        ],
        "third-party-requests": [
            "https://app-script.monsido.com/v2/monsido-script.js",
            "https://cdn.jsdelivr.net/npm/@unicorn-fail/drupal-bootstrap-styles@0.0.2/dist/3.4.0/8.x-3.x/drupal-trap",
            "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap.css",
            "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/js/bootstrap.js",
            "https://cdn.jsdelivr.net/npm/jquery-validation@1.17.0/dist/jquery.validate.min.js",
            "https://heatmaps.monsido.com/v1/heatmaps.js",
            "https://p.typekit.net/p.css?s=1&k=emv4hbp&ht=tk&f=6846.6848.6849.6851.6852.15910.15911.15912.40110.&a=7",
            "https://tracking.monsido.com/?a=g4KfyUhoEsjcoub-9hudmA&b=https%3A%2F%2Fzutphen.nl%2F&c=08B168319082d=12",
            "https://use.fontawesome.com/e6f0d6c9ef.css",
            "https://use.fontawesome.com/e6f0d6c9ef.js",
            "https://use.fontawesome.com/releases/v4.7.0/css/font-awesome-css.min.css",
            "https://use.fontawesome.com/releases/v4.7.0/fonts/fontawesome-webfont.woff2",
            "https://use.typekit.net/af/1b1b1e/00000000000000000001709e/27/l?primer=7cdcb44be4a7db8877ffa5c0007b5b3b",
            "https://use.typekit.net/af/3d6738/00000000000000003b9b237e/27/l?primer=7fa3915bdafdf03041871920a2051d72",
            "https://use.typekit.net/af/80c5d0/00000000000000000001709c/27/l?primer=7cdcb44be4a7db8877ffa5c0007b5b3b",
            "https://use.typekit.net/af/c630c3/000000000000000000017098/27/l?primer=7cdcb44be4a7db8877ffa5c0007b5b3b",
            "https://use.typekit.net/af/cafa63/00000000000000000001709a/27/l?primer=7cdcb44be4a7db8877ffa5c0007b5b3b",
            "https://use.typekit.net/af/d32e26/00000000000000000001709b/27/l?primer=7cdcb44be4a7db8877ffa5c0007b5b3b",
            "https://use.typekit.net/af/d69f58/00000000000000003b9b237d/27/l?primer=7fa3915bdafdf03041871920a2051d72",
            "https://use.typekit.net/emv4hbp.css",
            "https://www.google-analytics.com/analytics.js",
            "https://www.google-analytics.com/j/collect?v=1&_v=j100&aip=1&a=150306367&t=pageview&_s=1&dl=https%32Fzu",
        ],
        "third-party-domains": [
            "app-script.monsido.com",
            "cdn.jsdelivr.net",
            "heatmaps.monsido.com",
            "p.typekit.net",
            "tracking.monsido.com",
            "use.fontawesome.com",
            "use.typekit.net",
            "www.google-analytics.com",
        ],
        "third-party-top-level-domains": [
            "fontawesome.com",
            "google-analytics.com",
            "jsdelivr.net",
            "monsido.com",
            "typekit.net",
        ],
        "cookies": [
            {
                "name": "_ga",
                "value": "GA1.2.751199213.1683190826",
                "domain": ".zutphen.nl",
                "path": "/",
                "expires": 1717750826.487979,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "_gid",
                "value": "GA1.2.1001128005.1683190826",
                "domain": ".zutphen.nl",
                "path": "/",
                "expires": 1683277226,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "_gat",
                "value": "1",
                "domain": ".zutphen.nl",
                "path": "/",
                "expires": 1683190886,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "monsido",
                "value": "08B1683190826566",
                "domain": "zutphen.nl",
                "path": "/",
                "expires": 1685782826,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
        ],
        "timeless-cookies": [
            {
                "name": "_ga",
                "domain": ".zutphen.nl",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "_gat",
                "domain": ".zutphen.nl",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "_gid",
                "domain": ".zutphen.nl",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
            {
                "name": "monsido",
                "domain": "example.com",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            },
        ],
        "headers": {
            "cache-control": "must-revalidate, no-cache, private",
            "content-language": "nl",
            "content-type": "text/html; charset=UTF-8",
            "date": "Thu, 04 May 2023 09:00:28 GMT",
            "expires": "Sun, 19 Nov 1978 05:00:00 GMT",
            "link": '<https://zutphen.nl/>; rel="canonical", <https://zutphen.nl/>; rel="shortlink"',
            "permissions-policy": "interest-cohort=()",
            "referrer-policy": "strict-origin",
            "server": "Apache/2",
            "strict-transport-security": "max-age=31536000",
            "vary": "User-Agent",
            "x-content-type-options": "nosniff",
            "x-drupal-cache": "MISS",
            "x-drupal-dynamic-cache": "MISS",
            "x-frame-options": "SAMEORIGIN",
            "x-generator": "Drupal 9 (https://www.drupal.org)",
            "x-powered-by": "PHP/7.4.33",
            "x-ua-compatible": "IE=edge",
        },
        "security_details": {
            "issuer": "certSIGN Enterprise CA Class 3 G2",
            "protocol": "TLS 1.3",
            "subjectName": "zutphen.nl",
            "validFrom": 1664957513,
            "validTo": 1696493513,
        },
        "status": 200,
        "error": None,
    }


def test_get_all_third_party_requests(settings, current_path, db):
    data = demo_data()
    third_party_domains = data["third-party-domains"]

    # red territory, although clearly tracking.monsido.com should be on here...
    # their info: . We may pass your information on to third parties designated by you, our third-party service
    #  providers and affiliates, our successors and assigns, and our subsidiaries and parent companies ... well
    trackers = get_known_trackers_from_urls(third_party_domains)

    ddiff = DeepDiff(
        trackers,
        [
            {
                "Category": "Content",
                "Company": "Adobe",
                "Platform": "https://typekit.com",
                "Tracking Url": "use.typekit.net",
            },
            {
                "Category": "Disconnect",
                "Company": "Google",
                "Platform": "http://www.google.com/",
                "Tracking Url": "google-analytics.com",
            },
        ],
        ignore_order=True,
        report_repetition=True,
    )

    assert ddiff == {}


def test_web_privacy_scan(db, requests_mock, current_path, caplog):
    create_sample_geoip()
    create_sample_domainip()

    requests_mock.get("http://localhost:31337/?site=https://zutphen.nl", json=demo_data())
    url = Url.objects.create(url="zutphen.nl")
    ep = Endpoint.objects.create(
        url=url, discovered_on=datetime.now(timezone.utc), port=443, protocol="https", ip_version=4
    )

    p = Product.objects.create(
        name="Google Analytics",
    )

    ProductCookieIndicator.objects.create(match_name="_ga", product=p)

    store(scan("https://zutphen.nl"), ep.id)

    # also cookies and the list of third party domains, and the derived cookie location metric
    # (todo: add other derived location metrics)
    assert EndpointGenericScan.objects.all().count() == 6

    assert (
        EndpointGenericScan.objects.all().filter(type="web_privacy_tracking").first().rating
        == "web_privacy_tracking_trackers_found"
    )

    assert EndpointGenericScan.objects.all().filter(type="location_cookies").first().rating == "location_medium"

    assert (
        EndpointGenericScan.objects.all().filter(type="web_privacy_third_party_requests").first().rating
        == "web_privacy_third_party_found"
    )

    meaning = EndpointGenericScan.objects.all().filter(type="web_privacy_cookies").first().meaning

    assert meaning["products"][0]["product_name"] == "Google Analytics"
    assert meaning["products"][0]["cookies"][0] == strip_irrelevant_cookie_fields(demo_data()["timeless-cookies"][0])
    assert meaning["locations"] == [
        {
            "applicable_cookies": [
                {
                    "domain": "example.com",
                    "httpOnly": False,
                    "name": "monsido",
                    "path": "/",
                    "sameSite": "Lax",
                    "secure": False,
                }
            ],
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "unknown",
                "found_location": {
                    "as_number": 1337,
                    "as_organization": "test organization",
                    "city_in_en": None,
                    "continent_code": "NA",
                    "country_iso_code": None,
                    "isp_ame": "Test Isp",
                    "network": "10.0.0.0/8",
                },
            },
            "rating": "location_medium",
        },
        # TODO: there is something weird with this testsuite that cuases the result below to not be
        # exist when running this test isolated, maybe something with the time_cache stuff??
        {
            "applicable_cookies": [
                {
                    "domain": "example.com",
                    "httpOnly": False,
                    "name": "monsido",
                    "path": "/",
                    "sameSite": "Lax",
                    "secure": False,
                }
            ],
            "domain": "example.com",
            "evidence": {
                "continent_rating": "unknown",
                "country_rating": "unknown",
                "found_location": {
                    "AS Number": -1,
                    "AS Organization": "",
                    "ISP Name": "",
                    "city": "",
                    "continent": "",
                    "country": "",
                    "network": "",
                },
            },
            "rating": "location_unknown",
        },
    ]


def test_truncate_long_post_data():
    # Some sites just post tons and tons of post data. This part of the code reduces this because otherwise it will
    # just never fit. Too bad some data is lost. There unfortunately is a max row size in mysql of 65,535 bytes.
    # And there will be this website that has over 65,535 bytes of data on evidence. This means it has to go to files.
    # and that is just terrible. Postgres has a 1.6TB row size. So perhaps it's time to switch.
    requests = [
        {
            "url": "https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/Create",
            "resource_type": "xhr",
            "method": "POST",
            "post_data": '["O43z0dpjhgX20SCx4KAo"]',
        },
        {
            "url": "https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/GenerateIT",
            "resource_type": "xhr",
            "method": "POST",
            "post_data": '["O43z0dpjhgX20SCx4KAo","$9mk5aTRRAAZmMFhTRjDeNUTsWzOFJ3unADkAIwj8RggJyNxJa-hSEECqXw6bA"]',
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.js",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.php?action_name=www.brabantsedelta.nl%2FHome%20%7C%20Brabant",
            "resource_type": "ping",
            "method": "POST",
            "post_data": None,
        },
    ]

    truncated_requests = truncate_long_post_data(requests, 20)

    assert truncated_requests == [
        {
            "url": "https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/Create",
            "resource_type": "xhr",
            "method": "POST",
            "post_data": '["O43z0dpjhgX20SCx4KAo"]',
        },
        {
            "url": "https://jnn-pa.googleapis.com/$rpc/google.internal.waa.v1.Waa/GenerateIT",
            "resource_type": "xhr",
            "method": "POST",
            "post_data": '["O43z0dpjhgX20SCx4K... truncated 69 characters',
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.js",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.php?action_name=www.brabantsedelta.nl%2FHome%20%7C%20Brabant",
            "resource_type": "ping",
            "method": "POST",
            "post_data": None,
        },
    ]


def test_remove_duplicate_third_party_requestss():
    requests = [
        {
            "url": "https://logging.simanalytics.nl/piwik.js",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.php?action_name=www.brabantsedelta.nl%2FHome%20%7C%20Brabants"
            "e%20Delta&idsite=818&rec=1&r=134959&h=23&m=10&s=11&url=https%3A%2F%2Fwww.brabantsedelta.nl%2F&_id=9"
            "2a4d58c16ebffa3&_idn=1&send_image=0&_refts=0&cookie=1&res=1280x720&dimension1=landing_page&cvar=%7B"
            "%221%22%3A%5B%22ContentType%22%2C%22landing_page%22%5D%7D&pv_id=pxKG5y&pf_net=108&pf_srv=53&pf_tfr="
            "19&pf_dm1=358&uadata=%7B%22fullVersionList%22%3A%5B%7B%22brand%22%3A%22Not%2FA)Brand%22%2C%22versio"
            "n%22%3A%2299.0.0.0%22%7D%2C%7B%22brand%22%3A%22HeadlessChrome%22%2C%22version%22%3A%22115.0.5790.24"
            "%22%7D%2C%7B%22brand%22%3A%22Chromium%22%2C%22version%22%3A%22115.0.5790.24%22%7D%5D%2C%22mobile%22"
            "%3Afalse%2C%22model%22%3A%22%22%2C%22platform%22%3A%22Linux%22%2C%22platformVersion%22%3A%224.15.0%"
            "22%7D",
            "resource_type": "ping",
            "method": "POST",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.php?action_name=www.brabantsedelta.nl%2FHome%20%7C%20Brabants"
            "e%20Delta&idsite=818&rec=1&r=417021&h=23&m=10&s=11&url=https%3A%2F%2Fwww.brabantsedelta.nl%2F&_id=9"
            "2a4d58c16ebffa3&_idn=0&send_image=0&_refts=0&cookie=1&res=1280x720&dimension1=landing_page&cvar=%7B"
            "%221%22%3A%5B%22ContentType%22%2C%22landing_page%22%5D%7D&pv_id=bfDaqA&pf_net=108&pf_srv=53&pf_tfr="
            "19&pf_dm1=358&uadata=%7B%22fullVersionList%22%3A%5B%7B%22brand%22%3A%22Not%2FA)Brand%22%2C%22versio"
            "n%22%3A%2299.0.0.0%22%7D%2C%7B%22brand%22%3A%22HeadlessChrome%22%2C%22version%22%3A%22115.0.5790.24"
            "%22%7D%2C%7B%22brand%22%3A%22Chromium%22%2C%22version%22%3A%22115.0.5790.24%22%7D%5D%2C%22mobile%22"
            "%3Afalse%2C%22model%22%3A%22%22%2C%22platform%22%3A%22Linux%22%2C%22platformVersion%22%3A%224.15.0%"
            "22%7D",
            "resource_type": "ping",
            "method": "POST",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/plugins/HeatmapSessionRecording/configs.php?idsite=818&trackerid=We"
            "4is6&url=https%3A%2F%2Fwww.brabantsedelta.nl%2F",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
    ]

    deduplicated_requests = remove_duplicate_third_party_requests(requests)
    assert deduplicated_requests == [
        {
            "url": "https://logging.simanalytics.nl/piwik.js",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/piwik.php?action_name=www.brabantsedelta.nl%2FHome%20%7C%20Brabants"
            "e%20Delta&idsite=818&rec=1&r=134959&h=23&m=10&s=11&url=https%3A%2F%2Fwww.brabantsedelta.nl%2F&_id=9"
            "2a4d58c16ebffa3&_idn=1&send_image=0&_refts=0&cookie=1&res=1280x720&dimension1=landing_page&cvar=%7B"
            "%221%22%3A%5B%22ContentType%22%2C%22landing_page%22%5D%7D&pv_id=pxKG5y&pf_net=108&pf_srv=53&pf_tfr="
            "19&pf_dm1=358&uadata=%7B%22fullVersionList%22%3A%5B%7B%22brand%22%3A%22Not%2FA)Brand%22%2C%22versio"
            "n%22%3A%2299.0.0.0%22%7D%2C%7B%22brand%22%3A%22HeadlessChrome%22%2C%22version%22%3A%22115.0.5790.24"
            "%22%7D%2C%7B%22brand%22%3A%22Chromium%22%2C%22version%22%3A%22115.0.5790.24%22%7D%5D%2C%22mobile%22"
            "%3Afalse%2C%22model%22%3A%22%22%2C%22platform%22%3A%22Linux%22%2C%22platformVersion%22%3A%224.15.0%"
            "22%7D",
            "resource_type": "ping",
            "method": "POST",
            "post_data": None,
        },
        {
            "url": "https://logging.simanalytics.nl/plugins/HeatmapSessionRecording/configs.php?idsite=818&trackerid=We"
            "4is6&url=https%3A%2F%2Fwww.brabantsedelta.nl%2F",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
    ]


def test_worse_rating():
    # left > right
    assert (
        worse_rating(WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_HIGH, WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM)
        == WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_HIGH
    )

    # right > left
    assert (
        worse_rating(WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_OK, WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM)
        == WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM
    )

    # identical
    assert (
        worse_rating(WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM, WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM)
        == WEB_PRIVACY_COOKIE_PRODUCTS_NO_CONSENT_MEDIUM
    )

    # not existing, crash
    with pytest.raises(ValueError):
        assert worse_rating("appel", "ei")


@override_config(COOKIE_WHEN_RECEIVED_WITHOUT_CONSENT_PURPOSES_MEDIUM=["marketing"])
def test_product_meaning_from_cookies(db):
    v = ProductVendor.objects.create(name="Google")
    p = Product.objects.create(
        name="Google Analytics",
        vendor=v,
    )

    p2 = Product.objects.create(
        name="OWA",
    )

    marketing_cookie = CookiePurpose.objects.create(name="marketing")
    session_cookie = CookiePurpose.objects.create(name="session")

    ProductCookieIndicator.objects.create(match_name="_gat?", product=p, most_significant_purpose=marketing_cookie)
    ProductCookieIndicator.objects.create(
        match_name="cookieTest", match_path="/owa/auth.*", product=p2, most_significant_purpose=session_cookie
    )

    # Happens to be one rule for the same product, that does not always need to be the case.
    # They can also have multiple purposes, one per indicator.
    cookies = demo_data()["timeless-cookies"]
    assert product_meaning_from_cookies(cookies) == {
        "products": [
            {
                "cookies": [
                    {
                        "domain": ".zutphen.nl",
                        "indicator": 1,
                        "name": "_ga",
                        "path": "/",
                        "purpose": "marketing",
                        "purpose_rating": "medium",
                    },
                    {
                        "domain": ".zutphen.nl",
                        "indicator": 1,
                        "name": "_gat",
                        "path": "/",
                        "purpose": "marketing",
                        "purpose_rating": "medium",
                    },
                ],
                "product_id": 1,
                "product_name": "Google Analytics",
                "product_vendor_id": 1,
                "product_vendor_name": "Google",
                "product_version": "unknown",
            }
        ],
        "worst_purpose_rating": "medium",
    }

    owa_cookies = [
        {
            "name": "cookieTest",
            "path": "/owa/auth/example.com",
            "domain": "example.com",
        },
        {
            "name": "cookieTest",
            "path": "/",
            "domain": "example.com",
        },
    ]
    assert product_meaning_from_cookies(owa_cookies) == {
        "products": [
            {
                "product_id": p2.id,
                "product_name": "OWA",
                "product_vendor_id": None,
                "product_vendor_name": None,
                "product_version": "unknown",
                "cookies": [
                    {
                        "domain": "example.com",
                        "indicator": 2,
                        "name": "cookieTest",
                        "path": "/owa/auth/example.com",
                        "purpose": "session",
                        "purpose_rating": "ok",
                    }
                ],
            }
        ],
        "worst_purpose_rating": "ok",
    }


def test_web_privacy_scan_update(db, requests_mock, current_path, caplog):
    """Update endpointgenericscan object after updating indicators should result in
    location and product information being added."""
    requests_mock.get("http://localhost:31337/?site=https://zutphen.nl", json=demo_data())
    url = Url.objects.create(url="zutphen.nl")
    ep = Endpoint.objects.create(
        url=url, discovered_on=datetime.now(timezone.utc), port=443, protocol="https", ip_version=4
    )

    store(scan("https://zutphen.nl"), ep.id)

    assert EndpointGenericScan.objects.all().count() == 6

    meaning = EndpointGenericScan.objects.all().filter(type="web_privacy_cookies").first().meaning
    assert meaning["products"] == []
    assert meaning["locations"] == []
    assert EndpointGenericScan.objects.all().filter(type="location_cookies").first().meaning["locations"] == []
    assert EndpointGenericScan.objects.all().filter(type="web_privacy_products").first().meaning["products"] == []

    update_meaning_of_location_and_products_at_web_privacy_cookies()

    assert EndpointGenericScan.objects.all().count() == 8

    meaning = EndpointGenericScan.objects.all().filter(type="web_privacy_cookies").first().meaning
    assert meaning["products"] == []
    assert meaning["locations"] == []
    assert EndpointGenericScan.objects.all().filter(type="location_cookies").first().meaning["locations"] == []
    assert EndpointGenericScan.objects.all().filter(type="web_privacy_products").first().meaning["products"] == []

    # add location and product cookie indicators
    create_sample_geoip()
    create_sample_domainip()
    p = Product.objects.create(name="Google Analytics")
    ProductCookieIndicator.objects.create(match_name="_ga", product=p)

    # update again
    update_meaning_of_location_and_products_at_web_privacy_cookies()

    # everything should now be there
    assert EndpointGenericScan.objects.all().count() == 11

    meaning = EndpointGenericScan.objects.all().filter(type="web_privacy_cookies").first().meaning
    assert meaning["products"][0]["product_name"] == "Google Analytics"
    assert meaning["locations"] == [
        {
            "applicable_cookies": [
                {
                    "domain": "example.com",
                    "httpOnly": False,
                    "name": "monsido",
                    "path": "/",
                    "sameSite": "Lax",
                    "secure": False,
                }
            ],
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "unknown",
                "found_location": {
                    "as_number": 1337,
                    "as_organization": "test organization",
                    "city_in_en": None,
                    "continent_code": "NA",
                    "country_iso_code": None,
                    "isp_ame": "Test Isp",
                    "network": "10.0.0.0/8",
                },
            },
            "rating": "location_medium",
        },
        # TODO: there is something weird with this testsuite that cuases the result below to not be
        # exist when running this test isolated, maybe something with the time_cache stuff??
        {
            "applicable_cookies": [
                {
                    "domain": "example.com",
                    "httpOnly": False,
                    "name": "monsido",
                    "path": "/",
                    "sameSite": "Lax",
                    "secure": False,
                }
            ],
            "domain": "example.com",
            "evidence": {
                "continent_rating": "unknown",
                "country_rating": "unknown",
                "found_location": {
                    "AS Number": -1,
                    "AS Organization": "",
                    "ISP Name": "",
                    "city": "",
                    "continent": "",
                    "country": "",
                    "network": "",
                },
            },
            "rating": "location_unknown",
        },
    ]
    assert EndpointGenericScan.objects.all().filter(type="location_cookies").first().meaning["locations"] != []
    assert EndpointGenericScan.objects.all().filter(type="web_privacy_products").first().meaning["products"] != []
