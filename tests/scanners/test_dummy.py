"""Integration tests of scanner commands."""

import json

import pytest
from django.core.management import call_command

TEST_ORGANIZATION = 'faalonië'
NON_EXISTING_ORGANIZATION = 'faaloniet'


def test_dummy(responses, db, faalonië):
    """Test running dummy scan."""

    result = json.loads(call_command('scan-dummy-dumdum', '-v3', '-o', TEST_ORGANIZATION))

    assert result[0]['status'] == 'success'
