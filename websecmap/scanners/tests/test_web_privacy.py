from datetime import datetime, timezone

from constance.test.pytest import override_config
from deepdiff import DeepDiff
from freezegun import freeze_time

from websecmap.app import log
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.web_privacy import (
    NinetiesDatabase,
    extract_full_domain,
    get_third_party_requests,
    get_top_level_domains_from_database,
    import_scan_result_database_async,
    latest_visit_id,
    scan_and_store,
)
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


def test_get_all_third_party_requests(settings, current_path, db):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
        third_party_urls, third_party_domains = get_third_party_requests(
            2263104152409081, domain="zutphen.nl", domain_inc_subdomain="www.zutphen.nl"
        )

        # orange territory
        assert list(sorted(third_party_domains)) == list(
            sorted(
                [
                    "heatmaps.monsido.com",
                    "cdn.jsdelivr.net",
                    "p.typekit.net",
                    "app-script.monsido.com",
                    "tracking.monsido.com",
                    "use.typekit.net",
                    "use.fontawesome.com",
                    "www.google-analytics.com",
                ]
            )
        )

        assert list(sorted(third_party_urls)) == list(
            sorted(
                [
                    "https://use.typekit.net/af/1b1b1e/00000000000000000001709e/27/l?primer=7cdcb44be4a7db8877ffa5c0007"
                    "b8dd865b3bbc383831fe2ea177f62257a9191&fvd=n7&v=3",
                    "https://use.fontawesome.com/releases/v4.7.0/fonts/fontawesome-webfont.woff2",
                    "https://app-script.monsido.com/v2/monsido-script.js",
                    "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/js/bootstrap.js",
                    "https://use.typekit.net/af/d69f58/00000000000000003b9b237d/27/l?primer=7fa3915bdafdf03041871920a20"
                    "5bef951d72bf64dd4c4460fb992e3ecc3a862&fvd=n4&v=3",
                    "https://use.typekit.net/emv4hbp.css",
                    "https://use.fontawesome.com/releases/v4.7.0/css/font-awesome-css.min.css",
                    "https://tracking.monsido.com/?a=g4KfyUhoEsjcoub-9hudmA&b=https%3A%2F%2Fzutphen.nl%2F&c=D3716747574"
                    "09785&d=1366x768&f=2441674757409787&h=2",
                    "https://www.google-analytics.com/analytics.js",
                    "https://use.typekit.net/af/3d6738/00000000000000003b9b237e/27/l?primer=7fa3915bdafdf03041871920a20"
                    "5bef951d72bf64dd4c4460fb992e3ecc3a862&fvd=i4&v=3",
                    "https://cdn.jsdelivr.net/npm/jquery-validation@1.17.0/dist/jquery.validate.min.js",
                    "https://heatmaps.monsido.com/v1/heatmaps.js",
                    "https://use.fontawesome.com/e6f0d6c9ef.css",
                    "https://cdn.jsdelivr.net/npm/@unicorn-fail/drupal-bootstrap-styles@0.0.2/dist/3.4.0/8.x-3.x/drupal"
                    "-bootstrap.css",
                    "https://cdn.jsdelivr.net/npm/bootstrap@3.4.1/dist/css/bootstrap.css",
                    "https://use.typekit.net/af/cafa63/00000000000000000001709a/27/l?primer=7cdcb44be4a7db8877ffa5c0007"
                    "b8dd865b3bbc383831fe2ea177f62257a9191&fvd=n4&v=3",
                    "https://use.fontawesome.com/e6f0d6c9ef.js",
                    "https://use.typekit.net/af/d32e26/00000000000000000001709b/27/l?primer=7cdcb44be4a7db8877ffa5c0007"
                    "b8dd865b3bbc383831fe2ea177f62257a9191&fvd=i4&v=3",
                    "https://heatmaps.monsido.com/v1/settings/g4KfyUhoEsjcoub-9hudmA.json",
                    "https://p.typekit.net/p.css?s=1&k=emv4hbp&ht=tk&f=6846.6848.6849.6851.6852.15910.15911.15912.40110"
                    ".40112&a=734637&app=typekit&e=css",
                    "https://www.google-analytics.com/j/collect?v=1&_v=j99&aip=1&a=926472071&t=pageview&_s=1&dl=https%3"
                    "A%2F%2Fzutphen.nl%2F&ul=en-us&de=UTF-8&dt=Home%20%7C%20Gemeente%20Zutphen&sd=24-bit&sr=1366x768&vp"
                    "=1354x683&je=0&_u=aEBAAUABAAAAACAAI~&jid=520663373&gjid=615132089&cid=1600668312.1674757408&tid=UA"
                    "-29035364-1&_gid=1132515265.1674757408&_r=1&_slc=1&z=363073111",
                    "https://use.typekit.net/af/c630c3/000000000000000000017098/27/l?primer=7cdcb44be4a7db8877ffa5c0007"
                    "b8dd865b3bbc383831fe2ea177f62257a9191&fvd=n3&v=3",
                ]
            )
        )

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
                    "Category": "Analytics",
                    "Company": "Monsido",
                    "Platform": "https://monsido.com",
                    "Tracking Url": "tracking.monsido.com",
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


def test_nineties_db(current_path):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    db = NinetiesDatabase(db_location)
    value = db.first_value("SELECT visit_id FROM site_visits where visit_id = ?", [208321285225340])
    assert value == {"visit_id": 208321285225340}

    value = db.first_value("SELECT visit_id FROM site_visits where visit_id = ?", [1])
    assert value is None

    rows = db.rows("SELECT visit_id, browser_id FROM site_visits where visit_id < ?", [1912600925374354])
    assert rows == [
        {"visit_id": 208321285225340, "browser_id": 327863320},
        {"visit_id": 1378185009722149, "browser_id": 4271274354},
    ]


def test_latest_visit_id(db, current_path):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
        assert latest_visit_id("https://www.internet.nl/") == {"visit_id": 1378185009722149}
        assert latest_visit_id("https://nos.nl/") == {"visit_id": 208321285225340}
        assert latest_visit_id("http://nos.nl/") is None
        assert latest_visit_id("http://basisbeveiliging.nl/") == {"visit_id": 8782091711888075}
        assert latest_visit_id("http://www.basisbeveiliging.nl/") == {"visit_id": 8782091711888075}
        assert latest_visit_id("https://example.nl/") is None


def test_web_privacy_scan(db, requests_mock, current_path, caplog):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
        # not kicking off a scan, just continue by setting the response from WEB_PRIVACY_SERVER to {} instead of a wait
        requests_mock.post("http://localhost:31337/", json="{}")
        url = Url.objects.create(url="zutphen.nl")
        Endpoint.objects.create(
            url=url, discovered_on=datetime.now(timezone.utc), port=443, protocol="https", ip_version=4
        )
        scan_and_store([url.id])

        assert EndpointGenericScan.objects.all().count() == 2
        assert (
            EndpointGenericScan.objects.all().filter(type="web_privacy_tracking").first().rating
            == "web_privacy_tracking_trackers_found"
        )

        assert (
            EndpointGenericScan.objects.all().filter(type="web_privacy_third_party_requests").first().rating
            == "web_privacy_third_party_found"
        )


def test_get_top_level_domains_from_database(db, current_path):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
        with freeze_time("2023-01-28"):
            domains = get_top_level_domains_from_database()
            assert domains == [
                {"top_level_url": "http://www.basisbeveiliging.nl/", "visit_id": 8782091711888075},
                {"top_level_url": "http://www.internet.nl/", "visit_id": 1378185009722149},
                {"top_level_url": "http://basisbeveiliging.nl/", "visit_id": 8782091711888075},
                {"top_level_url": "https://basisbeveiliging.nl/", "visit_id": 8782091711888075},
                {"top_level_url": "https://www.internet.nl/", "visit_id": 1378185009722149},
                {"top_level_url": "http://www.nu.nl/", "visit_id": 4974794412559073},
                {"top_level_url": "https://www.nu.nl/", "visit_id": 4974794412559073},
                {"top_level_url": "https://arnhem.nl/", "visit_id": 1912600925374354},
                {"top_level_url": "https://zutphen.nl/", "visit_id": 2263104152409081},
                {"top_level_url": "https://eindhoven.nl/", "visit_id": 3938349430551297},
                {"top_level_url": "https://www.eindhoven.nl/", "visit_id": 3938349430551297},
                {"top_level_url": "https://nos.nl/", "visit_id": 208321285225340},
            ]

        # Here you'll find nothing because the results are too new and too old...
        with freeze_time("2022-01-24"):
            domains = get_top_level_domains_from_database()
            assert domains == []

        with freeze_time("2024-01-24"):
            domains = get_top_level_domains_from_database()
            assert domains == []


def test_extract_full_domain():
    assert extract_full_domain("https://www.basisbeveiliging.nl") == "www.basisbeveiliging.nl"
    assert extract_full_domain("https://basisbeveiliging.nl") == "basisbeveiliging.nl"
    assert extract_full_domain("https://basisbeveiliging.nl/#test/") == "basisbeveiliging.nl"


def test_import_scan_result_database_empty(db, current_path):
    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with freeze_time("2023-01-28"):
        with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
            # imports nothing, as there is nothing in the database:
            import_scan_result_database_async()
            assert EndpointGenericScan.objects.all().count() == 0


def test_import_scan_result_database_full(db, current_path):
    # will add 2 metrics every domain from the dataset...

    db_location = f"{current_path}/websecmap/scanners/tests/web_privacy/crawl-data.sqlite"

    with freeze_time("2023-01-28"):
        with override_config(WEB_PRIVACY_DATABASE_LOCATION=db_location):
            # Add a bunch of domains and endpoints, it will add results for each of them
            # Only add those for domains where scans started with https, as the scanning is restricted to https.
            domains = [
                "basisbeveiliging.nl",
                "www.internet.nl",
                "www.nu.nl",
                "arnhem.nl",
                "zutphen.nl",
                "eindhoven.nl",
                "www.eindhoven.nl",
                "nos.nl",
            ]
            for domain in domains:
                url = Url.objects.create(url=domain)
                Endpoint.objects.create(
                    url=url, discovered_on=datetime.now(timezone.utc), port=443, protocol="https", ip_version=4
                )

            # every privacy scan ads two metrics now, given the get_top_level_domains will add the above domains
            # * 2 results
            import_scan_result_database_async()
            # www.internet.nl, nu.nl is in the above dataset twice, basisbeveiliging.nl as well,

            # each of the domains should have 2 results, either neutral or with an issue.
            for domain in domains:
                log.debug("Checking if domain has two scans: %s", domain)
                url = Url.objects.all().filter(url=domain).first()
                log.debug(url)
                ep = Endpoint.objects.filter(url=url).first()
                log.debug(ep)
                assert EndpointGenericScan.objects.all().filter(endpoint=ep).count() == 2  # 20...
