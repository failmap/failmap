from typing import List

from websecmap.app.constance import constance_cached_value

CELERY_IP_VERSION_QUEUE_NAMES = {4: "ipv4", 6: "ipv6"}
# shorthand to produce nicer code
IP_QUEUES = CELERY_IP_VERSION_QUEUE_NAMES


def get_nameservers() -> List[str]:
    """Allow to overwrite nameservers from config or provide empty list to fallback to system DNS."""
    nameservers = constance_cached_value("SCANNER_NAMESERVERS")
    return nameservers or None


def in_chunks(my_list, chunk_length):
    # Example: chunks = list(chunks(urls, 25))
    # creates list of lists containing N items.
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), chunk_length):
        # Create an index range for l of n items:
        yield my_list[i : i + chunk_length]
