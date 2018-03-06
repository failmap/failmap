# Perform different types of dummy scanner runs from a user level (using failmap command)

import json
from subprocess import check_output

import pytest


@pytest.mark.parametrize('method', ['direct', 'sync', 'async'])
def test_scan_method(method, worker, faalonië):
    """Runs the scanner using each of the three methods."""

    if method == 'direct':
        pytest.skip("direct execution method currently not supported with dramatiq")

    output_json = check_output(
        'failmap scan_dummy -m {method} -o faalonië'.format(method=method).split(' '), encoding='utf8')
    output = json.loads(output_json)

    # async required extra command to wait for and retrieve result
    if method == 'async':
        pytest.skip("async result fetching currently not supported with dramatiq")

        task_id = output[0]

        output_json = check_output(
            'failmap scan_dummy -t {task_id}'.format(task_id=task_id).split(' '), encoding='utf8')
        output = json.loads(output_json)

    assert len(output) == 1, "Only one result is expected from fixture."
    result = output[0]

    # test output is a task response and account for the both success or failure responses as the tasks
    assert isinstance(result, dict) and ('status' in result or 'error' in result)
