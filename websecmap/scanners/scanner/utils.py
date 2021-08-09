import json
from random import choice  # nosec, no cryptography expected here
from typing import List

from websecmap.app.constance import constance_cached_value


CELERY_IP_VERSION_QUEUE_NAMES = {4: "ipv4", 6: "ipv6"}


# Cloudflare: 1.0.0.1, 1.1.1.1
# Google: 8.8.4.4, 8.8.8.8
# Quad9: 9.9.9.9
# Norton: 199.85.127.10, 199.85.126.10
# Comodo: 8.26.56.26, 8.20.247.20
# Cisco: 208.67.222.222
FALLBACK_DNS_SERVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222", "8.26.56.26"]


def get_nameservers() -> List[str]:
    nameservers = json.loads(constance_cached_value("SCANNER_NAMESERVERS"))
    return nameservers if nameservers else FALLBACK_DNS_SERVERS


def get_random_nameserver() -> str:
    return choice(get_nameservers())


def in_chunks(my_list, n):
    # Example: chunks = list(chunks(urls, 25))
    # creates list of lists containing N items.
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), n):
        # Create an index range for l of n items:
        yield my_list[i : i + n]
