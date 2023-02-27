import json

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

        evidence = """[{"template":"technologies/wordpress/plugins/tinymce-advanced.yaml","template-url":"https://github.com/projectdiscovery/nuclei-templates/blob/master/technologies/wordpress/plugins/tinymce-advanced.yaml","template-id":"wordpress-tinymce-advanced","template-path":"/Users/stitch/nuclei-templates/technologies/wordpress/plugins/tinymce-advanced.yaml","info":{"name":"Advanced Editor Tools (previously TinyMCE Advanced) Detection","author":["ricardomaia"],"tags":["tech","wordpress","wp-plugin","top-100","top-200"],"reference":["https://wordpress.org/plugins/tinymce-advanced/"],"severity":"info","metadata":{"plugin_namespace":"tinymce-advanced","wpscan":"https://wpscan.com/plugin/tinymce-advanced"}},"matcher-name":"outdated_version","type":"http","host":"https://elgerjonker.nl","matched-at":"https://elgerjonker.nl/wp-content/plugins/tinymce-advanced/readme.txt","extracted-results":["4.6.7"],"meta":{"last_version":"5.6.0"},"ip":"149.210.204.105","timestamp":"2023-02-27T11:33:16.019022+01:00","curl-command":"curl -X 'GET' -d '' -H 'Accept: */*' -H 'Accept-Language: en' -H 'User-Agent: Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36' 'https://elgerjonker.nl/wp-content/plugins/tinymce-advanced/readme.txt'","matcher-status":true,"matched-line":null}]"""  # noqa

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
        assert data == [
            {
                "organization_name": "test",
                "organization_id": 1,
                "url_url": "test.nl",
                "subdomain": "",
                "domain": "test.nl",
                "last_scan_moment": now,
                "rating_determined_on": now,
                "portals": json.loads(evidence),
            }
        ]
