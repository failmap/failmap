import json
from random import choice  # nosec, no cryptography expected here
from typing import List

from websecmap.app.constance import constance_cached_value

CELERY_IP_VERSION_QUEUE_NAMES = {4: "ipv4", 6: "ipv6"}
CELERY_IP_ALT_VERSION_QUEUE_NAMES = {4: "alt_ipv4", 6: "alt_ipv6"}

# https://www.nic.cz/page/4219/kopie-otevrene-dnssec-validujici-resolvery/)
DNS_CZ_NIC_V4 = ["193.17.47.1", "185.43.135.1"]
DNS_CZ_NIC_V6 = ["2001:148f:ffff::1", "2001:148f:fffe::1"]

# https://www.dns0.eu/
DNS_ZERO_EU_v4 = ["193.110.81.0", "185.253.5.0"]
DNS_ZERO_EU_V6 = ["2a0f:fc80::", "2a0f:fc81::"]

# https://www.quad9.net/service/service-addresses-and-features/
DNS_QUAD9_V4 = ["9.9.9.9", "149.112.112.112"]
DNS_QUAD9_V6 = ["2620:fe::fe", "2620:fe::9"]

# combines to:
# ["193.17.47.1", "185.43.135.1", "193.110.81.0", "185.253.5.0", "9.9.9.9", "149.112.112.112", "2001:148f:ffff::1",
# "2001:148f:fffe::1", "2a0f:fc80::", "2a0f:fc81::", "2620:fe::fe", "2620:fe::9"]
FALLBACK_DNS_SERVERS = DNS_CZ_NIC_V4 + DNS_ZERO_EU_v4 + DNS_QUAD9_V4 + DNS_CZ_NIC_V6 + DNS_ZERO_EU_V6 + DNS_QUAD9_V6


def get_nameservers() -> List[str]:
    nameservers = json.loads(constance_cached_value("SCANNER_NAMESERVERS"))
    return nameservers or FALLBACK_DNS_SERVERS


def get_random_nameserver() -> str:
    return choice(get_nameservers())


def in_chunks(my_list, chunk_length):
    # Example: chunks = list(chunks(urls, 25))
    # creates list of lists containing N items.
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), chunk_length):
        # Create an index range for l of n items:
        yield my_list[i : i + chunk_length]
