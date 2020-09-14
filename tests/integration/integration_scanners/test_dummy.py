# Perform different types of dummy scanner runs from a user level (using websecmap command)

import json
from subprocess import check_output

import pytest


# The following error will happen if you run a worker while running tests, using the same broker: different databases
# will be used and there will be exceptions like this one, the tests will hang forever.
# eventlet-async is not testable: {'error': 'DatabaseError', 'message':
# "DatabaseWrapper objects created in a thread can only
# be used in that same thread. The object with alias 'default' was created in thread id 140582651898312 and this is
# thread id 140582746599800."} is None
# Eventlet sync will hang forever.
# tests/integration/integration_scanners/test_dummy.py::test_scan_method[prefork-direct] PASSED [ 62%]
# tests/integration/integration_scanners/test_dummy.py::test_scan_method[prefork-sync] PASSED [ 75%]
# tests/integration/integration_scanners/test_dummy.py::test_scan_method[eventlet-direct] PASSED [ 87%]
# tests/integration/integration_scanners/test_dummy.py::test_scan_method[eventlet-sync]
# also removed the sync test, as we never use sync. This will probably cause problems down the road, but there
# is no time or budget to fix it now.
@pytest.mark.parametrize("method", ["direct"])
def test_scan_method(method, worker, faaloniae_integration):
    """Runs the scanner using each of the three methods."""

    output_json = check_output(
        "websecmap scan dummy -m {method} -o faalonië".format(method=method).split(" "), encoding="utf8"
    )
    output = json.loads(output_json)

    # async required extra command to wait for and retrieve result
    if method == "async":
        task_id = output[0]

        output_json = check_output(
            "websecmap scan dummy -t {task_id}".format(task_id=task_id).split(" "), encoding="utf8"
        )
        output = json.loads(output_json)

    assert len(output) == 1, "Only one result is expected from fixture."
    result = output[0]

    # test output is a task response and account for the both success or failure responses as the tasks
    # assert isinstance(result, dict) and ('status' in result or 'error' in result)

    # newer tasks are all 'finished' and deliver 'none'
    assert result is None


def text(filepath: str):
    with open(filepath, "r") as f:
        data = f.read()
    return data
