"""Integration tests of scanner commands."""

import json

from django.core.management import call_command

TEST_ORGANIZATION = 'faalonië'
NON_EXISTING_ORGANIZATION = 'faaloniet'


def test_dummy(responses, db, faalonië):
    """Test running dummy scan."""

    result = json.loads(call_command('scan', 'dummy', '-v3', '-o', TEST_ORGANIZATION))

    # dummy returns random success/failure results, only check if there is a result, not the result itself
    assert result[0]
