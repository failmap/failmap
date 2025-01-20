# todo: move this up in the conftest levels, aka: higher directory does not warrent redefines??
import pytest
from django.core.management import call_command

import websecmap


@pytest.fixture
def default_scan_metadata():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "scanmetadata", verbosity=0)


@pytest.fixture
def default_policy():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "default_policy", verbosity=0)


@pytest.fixture
def urlreduction_sample_data():
    call_command("loaddata", "urlreduction_sample_data", verbosity=0)


@pytest.fixture
def patch_resolve():
    def mock_resolves(param):
        return True

    websecmap.scanners.scanner.http.resolves = mock_resolves


@pytest.fixture
def reset_time_cache():
    websecmap.reporting.time_cache.reset()
