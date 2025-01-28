import json
from pathlib import Path

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.cookie_consent import store
from websecmap.scanners.scanner.web_privacy_crawled import (
    get_latest_scan_sessions_per_endpoint_with_and_without_consent,
    load_cookie_from_string,
    store_session_as_regular_metrics,
    try_load_json,
)


def test_get_latest_scan_sessions_per_endpoint_with_and_without_consent(db):
    # nothing in db is nothing to see here:
    data = get_latest_scan_sessions_per_endpoint_with_and_without_consent()
    assert data == {}

    # save the first one in the db, wihtout consent by default.
    url = Url(url="example.com")
    url.save()
    endpoint = Endpoint(url=url, protocol="https")
    endpoint.save()

    # playwright-privacy/ $ make run
    # curl -sf "http://localhost:31337/cookieconsent?site=https://tweakers.net:443&depth=2&maxpages=10" \
    # | jq . > tweakers_result.json
    result = json.loads((Path(__file__).parent / "tweakers_result.json").read_text())

    without_consent_session_id = store(result, endpoint.id)

    data = get_latest_scan_sessions_per_endpoint_with_and_without_consent()

    assert data == {endpoint.id: {"with_consent": None, "without_consent": without_consent_session_id}}

    # now save it with consent and see that this is reflected
    result["meta"]["stats"]["consent"] = True
    result["meta"]["session_id"] = 42
    with_consent_session_id = store(result, endpoint.id)

    data = get_latest_scan_sessions_per_endpoint_with_and_without_consent()
    assert data == {
        endpoint.id: {"with_consent": with_consent_session_id, "without_consent": without_consent_session_id}
    }

    # saving a newer result makes that appear in the dataset, the old one is not used as only the latest
    # scan is included.
    result["meta"]["session_id"] = 43
    new_with_consent_session_id = store(result, endpoint.id)

    data = get_latest_scan_sessions_per_endpoint_with_and_without_consent()
    assert data == {
        endpoint.id: {"with_consent": new_with_consent_session_id, "without_consent": without_consent_session_id}
    }


def test_store_session_as_regular_metrics(db, default_scan_metadata, default_policy):
    url = Url(url="example.com")
    url.save()
    endpoint = Endpoint(url=url, protocol="https")
    endpoint.save()

    # playwright-privacy/ $ make run
    # curl -sf "http://localhost:31337/cookieconsent?site=https://tweakers.net:443&depth=2&maxpages=10" \
    # | jq . > tweakers_result.json
    result = json.loads((Path(__file__).parent / "tweakers_result.json").read_text())

    # store already stores the values to the database, here there should be: tracking, third_party_request, and cookies
    # without consent.
    without_consent_session_id = store(result, endpoint.id)
    assert EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).count() == 4
    assert list(
        sorted(list(EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).values_list("type", flat=True)))
    ) == list(
        sorted(
            [
                "web_privacy_third_party_requests_crawled_no_consent",
                "web_privacy_tracking_crawled_no_consent",
                "web_privacy_cookies_crawled_no_consent",
                "web_privacy_third_party_domains_crawled_no_consent",
            ]
        )
    )

    # as things are deduped no new metrics should have been added here(!)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    assert EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).count() == 4

    # note that the store methods are also tested elsewhere.

    # check if the cookies are also in the created metric:
    scan = EndpointGenericScan.objects.filter(
        endpoint_id=endpoint.id, type="web_privacy_cookies_crawled_no_consent"
    ).first()
    evidence = json.loads(scan.evidence)
    assert len(evidence) > 0

    # evidence is stable, id's are normalized
    assert evidence == [
        {
            "domain": "tweakersgear.net",
            "httpOnly": True,
            "name": ".Nop.Customer",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {
            "domain": "tweakersgear.net",
            "httpOnly": False,
            "name": "ApplicationGatewayAffinity",
            "path": "/",
            "sameSite": "Lax",
            "secure": False,
        },
        {
            "domain": "tweakersgear.net",
            "httpOnly": False,
            "name": "ApplicationGatewayAffinityCORS",
            "path": "/",
            "sameSite": "None",
            "secure": True,
        },
        {
            "domain": ".tweakers.net",
            "httpOnly": True,
            "name": "LastVisit",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSID", "path": "/", "sameSite": "Lax", "secure": False},
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSLB", "path": "/", "sameSite": "Lax", "secure": False},
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSOD", "path": "/", "sameSite": "Lax", "secure": False},
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSPV", "path": "/", "sameSite": "Lax", "secure": False},
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSRT", "path": "/", "sameSite": "Lax", "secure": False},
        {"domain": ".tweakers.net", "httpOnly": False, "name": "SSSC", "path": "/", "sameSite": "Lax", "secure": False},
        {
            "domain": ".tweakers.net",
            "httpOnly": True,
            "name": "SessionTime",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {
            "domain": ".youtube.com",
            "httpOnly": True,
            "name": "VISITOR_INFO1_LIVE",
            "path": "/",
            "sameSite": "None",
            "secure": True,
        },
        {"domain": ".youtube.com", "httpOnly": True, "name": "YSC", "path": "/", "sameSite": "None", "secure": True},
        {
            "domain": "tweakersgear.net",
            "httpOnly": False,
            "name": "_ALGOLIA",
            "path": "/",
            "sameSite": "Lax",
            "secure": False,
        },
        {
            "domain": ".tweakers.net",
            "httpOnly": False,
            "name": "__Secure-TnetID",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {
            "domain": ".tweakers.net",
            "httpOnly": False,
            "name": "_pk_id.<HASH_OR_ID>",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {
            "domain": "tweakersgear.net",
            "httpOnly": False,
            "name": "ai_session",
            "path": "/",
            "sameSite": "None",
            "secure": True,
        },
        {
            "domain": "tweakersgear.net",
            "httpOnly": False,
            "name": "ai_user",
            "path": "/",
            "sameSite": "None",
            "secure": True,
        },
        {
            "domain": ".tweakers.net",
            "httpOnly": True,
            "name": "ssa-did",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {
            "domain": ".tweakers.net",
            "httpOnly": True,
            "name": "ssa-sid",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
        {"domain": ".tweakers.net", "httpOnly": False, "name": "tbb", "path": "/", "sameSite": "Lax", "secure": True},
        {
            "domain": ".tweakers.net",
            "httpOnly": False,
            "name": "twk-theme",
            "path": "/",
            "sameSite": "Lax",
            "secure": True,
        },
    ]


def test_load_cookie_from_string():
    cookie = load_cookie_from_string(
        "{'name': 'JSESSIONID', 'domain': 'www.europaomdehoek.nl', "
        "'path': '/', 'httpOnly': True, 'secure': True, 'sameSite': 'Strict'}"
    )

    assert cookie is not None
    assert cookie["name"] == "JSESSIONID"


def test_try_load_json():
    data = try_load_json(
        '{"name": "JSESSIONID", "domain": "www.europaomdehoek.nl", '
        '"path": "/", "httpOnly": true, "secure": true, "sameSite": "Strict"}'
    )
    assert data != {}
    assert data["name"] == "JSESSIONID"
