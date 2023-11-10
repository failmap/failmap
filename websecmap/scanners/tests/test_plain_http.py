from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.plain_http import replace_memory_address_in_string, store


def test_replace_memory_address_in_string():
    result = replace_memory_address_in_string(
        "HTTPSConnectionPool(host='example.nl', port=443): "
        "Max retries exceeded with url: / (Caused by ConnectTimeoutError(<urllib3.connection.HTTPSConnection object "
        "at 0x7f2368f44310>, 'Connection to example.nl timed out. (connect timeout=15)'))"
    )
    assert result == (
        "HTTPSConnectionPool(host='example.nl', port=443): "
        "Max retries exceeded with url: / (Caused by ConnectTimeoutError(<urllib3.connection.HTTPSConnection object "
        "at 0xmemory_address>, 'Connection to example.nl timed out. (connect timeout=15)'))"
    )

    assert replace_memory_address_in_string("0x7f2368f44310") == "0xmemory_address"

    assert replace_memory_address_in_string("0x7f2368f44310 0x7f2368f44310") == "0xmemory_address 0xmemory_address"

    assert replace_memory_address_in_string("0xbarbiemovie") == "0xbarbiemovie"
    assert replace_memory_address_in_string("") == ""

    assert (
        replace_memory_address_in_string(
            '{"result": false, "error": "HTTPSConnectionPool(host=\'example.nl\', '
            "port=443): Max retries exceeded with url: / (Caused by ConnectTimeoutError(<urllib3.connection."
            "HTTPSConnection object at 0x7f2368f44310>, 'Connection to example.nl timed out. (connect timeout=15"
            ')\'))", "response_text": ""}'
        )
        == '{"result": false, "error": "HTTPSConnectionPool(host=\'example.nl\','
        " port=443): Max retries exceeded with url: / (Caused by ConnectTime"
        "outError(<urllib3.connection.HTTPSConnection object at "
        "0xmemory_address>, 'Connection to example.nl timed out. "
        '(connect timeout=15)\'))", "response_text": ""}'
    )


def test_plain_http_store(db):
    url = Url.objects.create(url="example.nl")
    ep = Endpoint.objects.create(url=url, port=80, protocol="http")

    # cannot connect, does not resolve etc...
    resolves = True
    can_connect_result = {
        "result": False,
        "error": "HTTPSConnectionPool(host='example.nl', port=443): Max retries exceeded with url: / "
        "(Caused by ConnectTimeoutError(<urllib3.connection.HTTPSConnection object at 0x7f2368f44310>, "
        "'Connection to example.nl timed out. (connect timeout=15)'))",
        "response_text": "",
    }
    redirects_to_safety = False, []
    results = resolves, can_connect_result, redirects_to_safety

    store(results, ep.id)

    assert EndpointGenericScan.objects.all().count() == 1

    epgs = EndpointGenericScan.objects.first()
    assert "0xmemory_address" in epgs.evidence
