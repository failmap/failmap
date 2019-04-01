from datetime import datetime

import pytz

from constance import config

constance_cache = {}


def constance_cached_value(key):
    # todo: add this to the constance codebase. Constance is highly inefficient: 1 query per value on each access.
    """
    Tries to minimize access to the database for constance. Every time you want a value, you'll get the latest value.

    That's great but not really needed: it takes 8 roundtrips per url, which is not slow but still slows things down.
    That means about 5000 * 8 database hits per rebuild. = 40.000, which does have an impact.

    This cache holds the value for ten minutes.

    :param key:
    :return:
    """
    now = datetime.now(pytz.utc).timestamp()
    expired = now - 600  # 10 minute cache, 600 seconds. So changes still affect a rebuild.

    if constance_cache.get(key, None):
        if constance_cache[key]['time'] > expired:
            return constance_cache[key]['value']

    # add value to cache, or update cache
    value = getattr(config, key)
    constance_cache[key] = {'value': value, 'time': datetime.now(pytz.utc).timestamp()}
    return value


def validate_constance_configuration(CONSTANCE_CONFIG, CONSTANCE_CONFIG_FIELDSETS):
    # Check for constance configuration issues:
    # All Fields defined above must be in the fieldsets.
    # See also: https://github.com/jazzband/django-constance/issues/293
    variables_in_fieldsets = [i for sub in [CONSTANCE_CONFIG_FIELDSETS[x] for x in CONSTANCE_CONFIG_FIELDSETS] for i in
                              sub]
    variables_in_config = [x for x in CONSTANCE_CONFIG]
    missing = set(variables_in_config) - set(variables_in_fieldsets)
    if missing:
        raise EnvironmentError("Constance config variables %s are missing in constance config fieldsets." % missing)

    # All fieldsets fields must be defined:
    missing = set(variables_in_fieldsets) - set(variables_in_config)
    if missing:
        raise EnvironmentError("Constance Fieldsets refer to missing fields: %s." % missing)
