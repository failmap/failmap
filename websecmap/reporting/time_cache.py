# Isn't this what redis is supposed to do? :)
from datetime import datetime, timezone

CACHE_DURATION_SECONDS = 600
CACHE = {}


def cache_get(key):
    expired = datetime.now(timezone.utc).timestamp() - CACHE_DURATION_SECONDS

    if CACHE.get(key, None):
        if CACHE[key]["time"] > expired:
            return CACHE[key]["value"]

        # do not save this stuff forever
        del CACHE[key]

    # A default None is of a bit tricky, as 'None' might also have been cached. Should this just raise an error?
    return None


def cache_set(key, value):
    CACHE[key] = {"value": value, "time": datetime.now(timezone.utc).timestamp()}
    return value


def reset():
    # don't know how to do this otherwise for now. Using a singleton class perhaps?
    global CACHE  # pylint: disable=global-statement
    CACHE = {}  # noqa
