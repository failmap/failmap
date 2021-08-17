from websecmap.scanners.scanner.http import connection_answer, get_random_user_agent


def test_connection_answer():

    a = connection_answer()
    assert a == {"result": False, "error": ""}

    a = connection_answer(True)
    assert a == {"result": True, "error": ""}

    a = connection_answer(True, TimeoutError("test"))
    assert a == {"result": True, "error": "TimeoutError"}

    a = connection_answer(True, "error_code")
    assert a == {"result": True, "error": "error_code"}


def test_get_random_user_agent():
    testdata = set()
    for _ in range(0, 1000):
        testdata.add(get_random_user_agent())
    assert len(testdata) > 2
