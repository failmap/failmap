from datetime import datetime

from django.utils import timezone
from freezegun import freeze_time

from websecmap.map.logic.login_plaza import login_plaza_data
from websecmap.organizations.models import OrganizationType, Organization, Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_login_plaza_data(db):
    with freeze_time("2022-01-24"):
        # no data, no crashes
        data = login_plaza_data("NL", "municipality")
        assert data == []

        # Prepare the data for a typical response
        organization_type, created = OrganizationType.objects.all().get_or_create(name="municipality")
        now = timezone.now()

        organization = Organization.objects.all().create(
            name="test", type=organization_type, country="NL", created_on=now, is_dead=False
        )
        organization.layers.add(organization_type)

        url = Url.objects.all().create(url="test.nl", created_on=now, is_dead=False, not_resolvable=False)

        # create the n-n connection between url and organization
        url.organization.add(organization)
        url.save()

        endpoint = Endpoint.objects.create(url=url, port=443, protocol="https")

        evidence = """[ { "name": "Citrix ADC Gateway Login Panel - Detect", "finding-name": "nuclei_citrix_adc_gateway_panel", "evidence": { "extracted-results": [], "matched-at": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html" } }, { "name": "NetScaler AAA Login Panel - Detect", "finding-name": "nuclei_netscaler_aaa_login", "evidence": { "extracted-results": [], "matched-at": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html" } } ]"""  # noqa

        EndpointGenericScan.objects.create(
            endpoint=endpoint,
            evidence=evidence,
            type="nuclei_exposed_panels",
            rating_determined_on=now,
            is_the_latest_scan=True,
            rating="info",
        )

        # retrieve a typical response based on the single metrics we have in the db.
        data = login_plaza_data("NL", "municipality")

        # id's change per database test, dont reset them:
        del data[0]["organization_id"]
        del data[1]["organization_id"]
        del data[0]["scan_id"]
        del data[1]["scan_id"]

        assert data == [
            {
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": [],
                "portal_name": "Citrix ADC Gateway Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/index.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
            },
            {
                "domain": "test.nl",
                "last_scan_moment": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "organization_name": "test",
                "portal_extracted": [],
                "portal_name": "NetScaler AAA Login Panel",
                "portal_url": "https://nsg1.vumc.nl:443/logon/LogonPoint/tmindex.html",
                "rating_determined_on": datetime(2022, 1, 24, 0, 0, tzinfo=timezone.utc),
                "subdomain": "",
                "url_url": "test.nl",
            },
        ]
