from datetime import datetime
from typing import List

import pytz
from constance import config

constance_cache = {}


def get_bulk_values(keys: List[str]):
    """
    Instead of a single key, this will allow you to get multiple (if not all) values in one go.
    This saves a ton of individual queries.

    :param keys:
    :return:
    """
    from constance import admin

    # retrieves everything, pretty quickly
    values = admin.get_values()

    # and now extract the keys we want to have
    return {k: values[k] for k in keys if k in values}


def constance_cached_value(key):
    """
    Tries to minimize access to the database for constance. Every time you want a value, you'll get the latest value.
    This, without running memcached, or using a django cache. The django in memory cache (what this is) is not
    recommended. You CAN use this cache if you are fine with a variable being retrieved every so often, but not all
    the time. -> This routine saves about 10.000 roundtrips to the database.

    That's great but not really needed: it takes 8 roundtrips per url, which is not slow but still slows things down.
    That means about 5000 * 8 database hits per rebuild. = 40.000, which does have an impact.

    This cache holds the value for ten minutes.

    :param key:
    :return:
    """
    now = datetime.now(pytz.utc).timestamp()
    expired = now - 600  # 10 minute cache, 600 seconds. So changes still affect a rebuild.

    if constance_cache.get(key, None):
        if constance_cache[key]["time"] > expired:
            return constance_cache[key]["value"]

    # add value to cache, or update cache
    value = getattr(config, key)
    constance_cache[key] = {"value": value, "time": datetime.now(pytz.utc).timestamp()}
    return value


def validate_constance_configuration(CONSTANCE_CONFIG, CONSTANCE_CONFIG_FIELDSETS):
    # Check for constance configuration issues:
    # All Fields defined above must be in the fieldsets.
    # See also: https://github.com/jazzband/django-constance/issues/293
    variables_in_fieldsets = [
        i for sub in [CONSTANCE_CONFIG_FIELDSETS[x] for x in CONSTANCE_CONFIG_FIELDSETS] for i in sub
    ]
    variables_in_config = [x for x in CONSTANCE_CONFIG]
    missing = set(variables_in_config) - set(variables_in_fieldsets)
    if missing:
        raise EnvironmentError("Constance config variables %s are missing in constance config fieldsets." % missing)

    # All fieldsets fields must be defined:
    missing = set(variables_in_fieldsets) - set(variables_in_config)
    if missing:
        raise EnvironmentError("Constance Fieldsets refer to missing fields: %s." % missing)
