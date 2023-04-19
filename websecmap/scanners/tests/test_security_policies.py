from datetime import timezone, datetime

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.security_policies import (
    initialize_security_policies,
    further_specify_security_policy,
    reset_security_policies,
)


def test_determine_security_policies(db):
    url = Url.objects.create(url="internetcleanup.foundation")
    ep = Endpoint.objects.create(
        url=url, port=443, protocol="https", ip_version=4, discovered_on=datetime.now(timezone.utc)
    )

    # this should set the service as a webserver:
    initialize_security_policies()

    assert ep.security_policies.count() == 1
    assert ep.security_policies_list == ["webserver"]

    # set the role to something else, it should not be set to webserver again:
    further_specify_security_policy(ep.id, "webserver", "json")
    assert ep.security_policies_list != ["webserver"]

    # reset the role to something else
    reset_security_policies(ep, "new_role")
    assert ep.security_policies_list == ["new_role"]
