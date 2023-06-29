from websecmap.scanners.comperators import compare_qsl_keys, compare_urls, compare_web_privacy_third_party_requests


def test_compare_post_data():
    old = (
        "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl&siteInfo%5Bcountry%5D=nl&action=new_buid&data%5Bcategory"
        "%5D=sm_fusion&data%5Baction%5D=new_buid&data%5BtimeOnPage%5D=0.023&data%5BpageType%5D=HP&data%5Bbuid%5D=S"
        "F1.9.0-ea545130-5bb5-4d82-92e6-9e64dc0abdac&data%5Bsuid%5D=c19bcc68-1e23-411e-9465-4901a0f51191&data%5Bpui"
        "d%5D=ad047b9e-882e-4471-b8ed-c0cc1a49f69c&data%5Burl%5D=https%3A%2F%2Fwww.x.nl%2F&data%5Breferral%5D=&da"
        "ta%5BfusionVersion%5D=1.9.0&data%5BeventSource%5D=tracker"
    )

    assert compare_qsl_keys(old, old) is True

    # same data
    assert (
        compare_qsl_keys(
            "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl", "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl"
        )
        is True
    )

    # change langauge, should be the comparable still as we dont care for the values
    assert (
        compare_qsl_keys(
            "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl",
            "siteInfo%5Bsite%5D=othersite&siteInfo%5Blanguage%5D=somethingcompletelydifferent",
        )
        is True
    )

    # change a parameter should be seen as a change
    assert (
        compare_qsl_keys(
            "siteInfo%5Bsite%5D=x&somethingcompletelydifferent%5Blanguage%5D=nl",
            "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl",
        )
        is False
    )

    # delete a parameter should be seen as a change
    assert compare_qsl_keys("siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl", "siteInfo%5Bsite%5D=x") is False

    # add a parameter should be seen as a change
    assert (
        compare_qsl_keys(
            "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl",
            "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl&somethingcompletelydifferent%5Blanguage%5D=nl",
        )
        is False
    )

    # this approach ofc breaks: then any changes are ignored since keys cannot be found


def test_compare_post_data_garbo():
    assert compare_qsl_keys("nsadnjkadsnlkasdklnadskln", "laknsdnasdnsadndasnkadsjinasdnoiadsnkl") is False
    assert compare_qsl_keys("a", "a") is True
    assert compare_qsl_keys(None, "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage") is False
    assert compare_qsl_keys(b"123", 123) is False


def test_compare_urls():
    assert compare_urls("https://www.x.nl/", "https://www.x.nl/") is True

    # different schema, subdomain, path, dir, so different url
    assert compare_urls("https://www.x.nl/", "http://www.x.nl/") is False
    assert compare_urls("https://www.x.nl/", "http://www.y.nl/") is False
    assert compare_urls("https://www.x.nl/", "https:/x.nl/") is False
    assert compare_urls("https://www.x.nl/", "https://www.x.nl/test/") is False

    # same parameters with different values should be the okay
    assert compare_urls("http://x.nl/?a=1", "http://x.nl/?a=2") is True
    # also with multiple different parameters in different orders
    assert compare_urls("http://x.nl/?a=1&b=2&c=3", "http://x.nl/?a=3&b=2&c=1") is True

    # different parameters, more or missing paramaters should not be ok
    assert compare_urls("http://x.nl/?a=1", "http://x.nl/?a=2&b=2") is False
    assert compare_urls("http://x.nl/?a=1", "http://x.nl/?b=2") is False
    assert compare_urls("http://x.nl/?a=1", "http://x.nl/") is False


def test_compare_urls_garbo():
    assert compare_urls("nsadnjkadsnlkasdklnadskln", "laknsdnasdnsadndasnkadsjinasdnoiadsnkl") is False
    assert compare_urls("a", "a") is False
    assert compare_urls(None, "https://www.x.nl/") is False
    assert compare_urls(b"123", 123) is False


def test_compare_web_privacy_third_party_requests():
    requests = [
        {
            "url": "https://script.shoppingminds.com/x_nl/index.js?_=1687874430050",
            "resource_type": "script",
            "method": "GET",
            "post_data": None,
        },
        {
            "url": "https://trkr.shoppingminds.net/api/x/x",
            "resource_type": "xhr",
            "method": "POST",
            "post_data": "siteInfo%5Bsite%5D=x&siteInfo%5Blanguage%5D=nl",
        },
    ]
    # the same data, so correct
    assert compare_web_privacy_third_party_requests(requests, requests) is True

    # data with different paramters everywhere where this is acceptable, in a different order should be fine
    assert (
        compare_web_privacy_third_party_requests(
            requests,
            [
                {
                    "url": "https://trkr.shoppingminds.net/api/x/x",
                    "resource_type": "xhr",
                    "method": "POST",
                    # different order, different values, but the same keys, should be fine
                    "post_data": "siteInfo%5Blanguage%5D=en&siteInfo%5Bsite%5D=x",
                },
                {
                    # different values in parameter should be fine
                    "url": "https://script.shoppingminds.com/x_nl/index.js?_=161111111111111150",
                    "resource_type": "script",
                    "method": "GET",
                    "post_data": None,
                },
            ],
        )
        is True
    )
