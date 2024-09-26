from itertools import islice
from typing import Any, Iterable

from websecmap.app.constance import constance_cached_value

CELERY_IP_VERSION_QUEUE_NAMES = {4: "ipv4", 6: "ipv6"}
# shorthand to produce nicer code
IP_QUEUES = CELERY_IP_VERSION_QUEUE_NAMES


def get_nameservers() -> list[str]:
    """Allow to overwrite nameservers from config or provide empty list to fallback to system DNS."""
    nameservers = constance_cached_value("SCANNER_NAMESERVERS")
    return nameservers or []


def in_chunks(my_list: list[Any], chunk_length: int) -> Iterable[Any]:
    # Example: chunks = list(chunks(urls, 25))
    # creates list of lists containing N items.
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), chunk_length):
        # Create an index range for l of n items:
        yield my_list[i : i + chunk_length]


# TODO: python 3.12
# def dict_chunks[T](my_dict: dict[str, T], chunk_length: int) -> Iterable[dict[str, T]]:
def dict_chunks(my_dict: dict[str, Any], chunk_length: int) -> Iterable[Any]:
    """
    >>> list(dict_chunks({'a':1, 'b':2, 'c':3}, 2))
    [{'a': 1, 'b': 2}, {'c': 3}]
    """
    keys = iter(my_dict)
    for _ in range(0, len(my_dict), chunk_length):
        yield {k: my_dict[k] for k in islice(keys, chunk_length)}
