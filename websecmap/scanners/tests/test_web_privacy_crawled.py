from pathlib import Path
import json

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.cookie_consent import store
from websecmap.scanners.scanner.web_privacy_crawled import (
    get_latest_scan_sessions_per_endpoint_with_and_without_consent,
    store_session_as_regular_metrics,
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
    assert EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).count() == 3
    assert list(
        sorted(list(EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).values_list("type", flat=True)))
    ) == list(
        sorted(
            [
                "web_privacy_third_party_requests_crawled_no_consent",
                "web_privacy_tracking_crawled_no_consent",
                "web_privacy_cookies_crawled_no_consent",
            ]
        )
    )

    # as things are deduped no new metrics should have been added here(!)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    store_session_as_regular_metrics(without_consent_session_id)
    assert EndpointGenericScan.objects.filter(endpoint_id=endpoint.id).count() == 3

    # note that the store methods are also tested elsewhere.
