from requests.structures import CaseInsensitiveDict

from websecmap.scanners.scanner.security_headers import get_headers


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


def test_get_headers(requests_mock):

    # Should just work with broken headers, but now seeing an MissingHeaderBodySeparatorDefect warning
    # probably the warning is just ignored, It's not trivial to simulate.
    # https://gvo.schiedam.nl
    broken_headers = {"Access-Control-Allow-Origin : https://gvo.schiedam.nl": "", "X-XSS-Protection": "1; mode=block"}
    requests_mock.get("", text="1", headers=broken_headers)

    data = get_headers("https://gvo.schiedam.nl", host="gvo.schiedam.nl")

    assert data == {"Access-Control-Allow-Origin : https://gvo.schiedam.nl": "", "X-XSS-Protection": "1; mode=block"}
