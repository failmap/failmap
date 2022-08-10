from websecmap.reporting import time_cache
from freezegun import freeze_time


def test_caching_ability():
    with freeze_time("2020-01-01"):
        data = time_cache.get("not existing")
        assert data is None

        # value can be set and cached
        value = "text_value"
        time_cache.set("my_key", value)
        assert time_cache.get("my_key") == value

        # value can be overwritten by another value
        value = {"key": "value", "dict": 1}
        time_cache.set("my_key", value)
        assert time_cache.get("my_key") == value

        # Value is not deleted after read
        assert time_cache.get("my_key") == value
        assert time_cache.get("my_key") == value

    # value is expired
    with freeze_time("2020-02-01"):
        assert time_cache.get("my_key") is None
