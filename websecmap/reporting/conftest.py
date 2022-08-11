import pytest
from django.core.management import call_command


@pytest.fixture
def default_policy():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "default_policy", verbosity=0)
