from datetime import timezone, datetime

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, SecurityPolicy

from websecmap.scanners.security_policies import add_policy_by_name, check_policy_sanity


def test_add_policy_by_name(db):
    url = Url.objects.create(url="internetcleanup.foundation")
    ep = Endpoint.objects.create(
        url=url, port=443, protocol="https", ip_version=4, discovered_on=datetime.now(timezone.utc)
    )
    add_policy_by_name(ep.id, "test")

    ep = Endpoint.objects.get(id=ep.id)
    assert ep.security_policies_list == ["test"]


def test_check_policy_sanity():
    assert check_policy_sanity(SecurityPolicy()) is False
    assert check_policy_sanity(SecurityPolicy(**{"common_ports": [443]})) is True
