from websecmap.scanners import init_dict


def test_init_dict():
    a = None
    b = None
    c = None
    d = None

    a = init_dict(a)
    assert a == {}

    a, b = init_dict(a, b)
    assert b == {}

    a, b, c = init_dict(a, b, c)
    assert c == {}

    a, b, c, d = init_dict(a, b, c, d)
    assert d == {}

    x = init_dict()
    assert x == ()

    # It should return values that are already set right

    a, b = init_dict({"a": 1}, None)
    assert a == {"a": 1}
    assert b == {}
