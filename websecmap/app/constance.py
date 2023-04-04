from datetime import datetime, timezone
from typing import List

from constance import config
from requests.structures import CaseInsensitiveDict

constance_cache = {}


def get_all_values() -> CaseInsensitiveDict:
    # Returned case insensitive to prevent hours of fun between caps and non-caps

    # solves: django.core.exceptions.AppRegistryNotReady: Apps aren't loaded yet.
    from constance import admin  # pylint: disable=import-outside-toplevel

    return CaseInsensitiveDict(admin.get_values())


def get_bulk_values(keys: List[str]):
    """
    Instead of a single key, this will allow you to get multiple (if not all) values in one go.
    This saves a ton of individual queries.

    :param keys:
    :return:
    """
    # solves: django.core.exceptions.AppRegistryNotReady: Apps aren't loaded yet.
    from constance import admin  # pylint: disable=import-outside-toplevel

    # retrieves everything, pretty quickly
    values = admin.get_values()

    # and now extract the keys we want to have
    return {k: values[k] for k in keys if k in values}


def get_bulk_values_starting_with(starts_with: str):
    # solves: django.core.exceptions.AppRegistryNotReady: Apps aren't loaded yet.
    from constance import admin  # pylint: disable=import-outside-toplevel

    # retrieves everything, pretty quickly
    values = admin.get_values()

    # and now extract the keys we want to have
    return {key: values[key] for key in values if key.startswith(starts_with)}


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
    now = datetime.now(timezone.utc).timestamp()
    expired = now - 600  # 10 minute cache, 600 seconds. So changes still affect a rebuild.

    if constance_cache.get(key, None):
        if constance_cache[key]["time"] > expired:
            return constance_cache[key]["value"]

    # add value to cache, or update cache
    value = getattr(config, key)
    constance_cache[key] = {"value": value, "time": datetime.now(timezone.utc).timestamp()}
    return value


def validate_constance_configuration(constance_config, constance_config_fieldsets):
    # Check for constance configuration issues:
    # All Fields defined above must be in the fieldsets.
    # See also: https://github.com/jazzband/django-constance/issues/293
    variables_in_fieldsets = [
        i for sub in [constance_config_fieldsets[x] for x in constance_config_fieldsets] for i in sub
    ]
    variables_in_config = list(constance_config)
    missing = set(variables_in_config) - set(variables_in_fieldsets)
    if missing:
        raise EnvironmentError(f"Constance config variables {missing} are missing in constance config fieldsets.")

    # All fieldsets fields must be defined:
    missing = set(variables_in_fieldsets) - set(variables_in_config)
    if missing:
        raise EnvironmentError(f"Constance Fieldsets refer to missing fields: {missing}.")
