from websecmap.app.constance import get_all_values


def test_get_all_values(db):
    values = get_all_values()

    assert len(values) > 10
    assert values["PROJECT_COUNTRY"] == "NL"
    assert values["PROJECT_country"] == "NL"
