from constance.test import override_config

from websecmap.app.constance import constance_cached_value, get_all_values


def test_get_all_values(db):
    values = get_all_values()

    assert len(values) > 10
    assert values["PROJECT_COUNTRY"] == "NL"
    assert values["PROJECT_country"] == "NL"


@override_config(COOKIE_WHEN_RECEIVED_WITHOUT_CONSENT_PURPOSES_MEDIUM=["marketing", "analytics"])
def test_json_value(db):
    # make sure a developer does not have to unmarshall the values when working with json fields.
    data = constance_cached_value("COOKIE_WHEN_RECEIVED_WITHOUT_CONSENT_PURPOSES_MEDIUM")
    assert data == ["marketing", "analytics"]
