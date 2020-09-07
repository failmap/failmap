# Perform different types of dummy scanner runs from a user level (using websecmap command)

import json
from subprocess import check_output

import pytest


# eventlet-async is not testable: {'error': 'DatabaseError', 'message': "DatabaseWrapper objects created in a thread can only
# be used in that same thread. The object with alias 'default' was created in thread id 140582651898312 and this is
# thread id 140582746599800."} is None
@pytest.mark.parametrize('method', ['direct', 'sync'])
def test_scan_method(method, worker, faaloniae):
    """Runs the scanner using each of the three methods."""

    output_json = check_output(
        'websecmap scan dummy -m {method} -o faalonië'.format(method=method).split(' '), encoding='utf8')
    output = json.loads(output_json)

    # async required extra command to wait for and retrieve result
    if method == 'async':
        task_id = output[0]

        output_json = check_output(
            'websecmap scan dummy -t {task_id}'.format(task_id=task_id).split(' '), encoding='utf8')
        output = json.loads(output_json)

    assert len(output) == 1, "Only one result is expected from fixture."
    result = output[0]

    # test output is a task response and account for the both success or failure responses as the tasks
    # assert isinstance(result, dict) and ('status' in result or 'error' in result)

    # newer tasks are all 'finished' and deliver 'none'
    assert result is None
