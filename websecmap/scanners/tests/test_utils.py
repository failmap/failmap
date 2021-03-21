from websecmap.scanners.scanner.utils import get_nameservers
from constance.test import override_config


@override_config(SCANNER_NAMESERVERS='["2.2.2.2", "3.3.3.3"]')
def test_get_nameservers_with_custom_config(db):
    # Name of this test is intended to go after test_get_nameservers due to cache being overridden.
    servers = get_nameservers()
    assert len(servers) == 2
    assert servers == ["2.2.2.2", "3.3.3.3"]
