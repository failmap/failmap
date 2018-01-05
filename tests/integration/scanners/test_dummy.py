# Perform different types of dummy scanner runs from a user level (using failmap command)

from subprocess import check_output

import pytest


@pytest.mark.parametrize('method', ['direct', 'sync', 'async'])
def test_scan_method(method, worker, faalonië):
    """Runs the scanner using each of the three methods."""

    output = check_output('failmap scan_dummy -m {method} -o faalonië'.format(method=method).split(' '))

    assert output
