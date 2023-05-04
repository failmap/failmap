from datetime import datetime, timezone

from deepdiff import DeepDiff

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.web_privacy import store, scan

from websecmap.scanners.scanner.web_privacy_resources.trackers import (
    get_known_trackers_from_urls,
    get_tracker_info_from_disconnectme,
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
                "domain": "zutphen.nl",
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

    requests_mock.get("http://localhost:31337/?site=https://zutphen.nl", json=demo_data())
    url = Url.objects.create(url="zutphen.nl")
    ep = Endpoint.objects.create(
        url=url, discovered_on=datetime.now(timezone.utc), port=443, protocol="https", ip_version=4
    )

    store(scan("https://zutphen.nl"), ep.id)

    # also cookies
    assert EndpointGenericScan.objects.all().count() == 3
    assert (
        EndpointGenericScan.objects.all().filter(type="web_privacy_tracking").first().rating
        == "web_privacy_tracking_trackers_found"
    )

    assert (
        EndpointGenericScan.objects.all().filter(type="web_privacy_third_party_requests").first().rating
        == "web_privacy_third_party_found"
    )
