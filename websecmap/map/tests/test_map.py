from websecmap.map.logic.map import clean_words


def test_clean_words():
    # dont' work with stuff that's only numbers and ips etc
    assert clean_words(["123-12-412.", "112", "12312312"]) == []

    # alphabetical order
    assert clean_words(["things", "somethingnice"]) == ["somethingnice", "things"]

    # too short
    assert clean_words(["a", "lp", "srt"]) == []

    # common
    assert clean_words(["enterpriseregistration"]) == []

    # forbidden parts
    assert clean_words(["kb-client 239", "kb-client 031"]) == []

    # anything more than two hypthens is usually not a human word but a system name
    assert clean_words(["kb-client-031", "kb-client-239"]) == []
