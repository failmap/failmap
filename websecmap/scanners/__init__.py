# RemovedInDjango41Warning: 'websecmap.scanners' defines default_app_config =
# 'websecmap.scanners.apps.ScannersConfig'. Django now detects this configuration automatically.
# You can remove default_app_config.
# default_app_config = "websecmap.scanners.apps.ScannersConfig"
from typing import Optional


ObjectFilter = dict[str, str]


def init_dict(*args: Optional[ObjectFilter]) -> tuple[ObjectFilter, ObjectFilter, ObjectFilter]:
    # To deal with the well known issues with mutable arguments in methods.
    # Initialize to empty dicts, so they can be used as kwargs and other constructs without having to deal with None
    # values all the time.

    returned = []

    for arg in args:
        if arg is None:
            returned.append({})
        else:
            returned.append(arg)

    if len(returned) == 1:
        return returned[0]

    return tuple(returned)
