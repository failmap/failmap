"""Integration tests of scanner commands."""

import json
import os

import pytest
from django.core.management import call_command

SECURITY_HEADERS = {
    'X-XSS-Protection': '1',
}

TEST_ORGANIZATION = 'faalonië'
NON_EXISTING_ORGANIZATION = 'faaloniet'


def test_security_headers(responses, db, faalonië):
    """Test running security headers scan."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', headers=SECURITY_HEADERS)

    result = json.loads(call_command('scan-security-headers', '-v3', '-o', TEST_ORGANIZATION))

    assert result[0]['status'] == 'success'


def test_security_headers_all(responses, db, faalonië):
    """Test defaulting to all organizations."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', headers=SECURITY_HEADERS)

    result = json.loads(call_command('scan-security-headers', '-v3'))

    assert result[0]['status'] == 'success'


def test_security_headers_notfound(responses, db, faalonië):
    """Test invalid organization."""

    with pytest.raises(Exception):
        call_command('scan-security-headers', '-v3', '-o', NON_EXISTING_ORGANIZATION)


def test_security_headers(responses, db, faalonië):
    """Test with failing endpoint."""

    responses.add(responses.GET, 'https://' + faalonië['url'].url + ':443/', status=500)

    result = json.loads(call_command('scan-security-headers', '-v3', '-o', TEST_ORGANIZATION))

    assert result[0]['cause']['error'] == 'HTTPError'
