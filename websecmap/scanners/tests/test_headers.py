from requests.structures import CaseInsensitiveDict


def test_CaseInsensitiveDict():
    # Headers are case insensitive, the request library has this awesome thing to work with that without altering
    # any checking logic. This verifies that the object does wat it promises.

    z = CaseInsensitiveDict()
    z["TEST"] = 1
    z["second_test"] = 2

    assert z["tesT"] == 1
    assert z["SeCoNd_TeSt"] == 2

    assert "TeSt" in z
    assert "teST" in z.keys()
    assert "nonsense" not in z.keys()
    assert "test2" not in z.keys()
    assert "test2" not in z
