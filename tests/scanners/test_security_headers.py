"""Integration tests of scanner commands."""

import json

from django.core.management import call_command

SECURITY_HEADERS = {
    'X-XSS-Protection': '1',
}

TEST_ORGANIZATION = 'faalonië'
NON_EXISTING_ORGANIZATION = 'faaloniet'


def test_security_headers(responses, db, faalonië):
    """Test running security headers scan."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', headers=SECURITY_HEADERS)

    result = json.loads(call_command('scan_security_headers', '-v3', '-o', TEST_ORGANIZATION))

    assert result[0]['status'] == 'success'


def test_security_headers_all(responses, db, faalonië):
    """Test defaulting to all organizations."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', headers=SECURITY_HEADERS)

    result = json.loads(call_command('scan_security_headers', '-v3'))

    assert result[0]['status'] == 'success'


def test_security_headers_notfound(responses, db, faalonië):
    """Test invalid organization."""

    # should work fine, it will start a scan on nothing, so it's done quickly :)
    result = json.loads(call_command('scan_security_headers', '-v3', '-o', NON_EXISTING_ORGANIZATION))
    # no crashes, just an empty result.
    assert result == []


# todo: could do a redirect test
def test_security_headers_failure(responses, db, faalonië):
    """Test with failing endpoint."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', status=500)

    result = json.loads(call_command('scan_security_headers', '-v3', '-o', TEST_ORGANIZATION))

    assert result[0]['status'] == 'success'
