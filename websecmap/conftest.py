# todo: move this up in the conftest levels, aka: higher directory does not warrent redefines??
from django.core.management import call_command
import pytest


@pytest.fixture
def default_scan_metadata():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "scanmetadata", verbosity=0)


@pytest.fixture
def default_policy():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "default_policy", verbosity=0)
  
