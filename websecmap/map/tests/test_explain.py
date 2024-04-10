from datetime import datetime, timezone

from freezegun import freeze_time

from websecmap.map.logic.explain import get_recent_explains
from websecmap.organizations.models import Organization, OrganizationType, Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan


def test_get_recent_explains(db, default_scan_metadata, default_policy):
    # no data, no crash:
    assert get_recent_explains("NL", "municipality") == []

    with freeze_time("2022-01-24"):
        # Prepare the data for a typical response
        organization_type, created = OrganizationType.objects.all().get_or_create(name="municipality")
        now = datetime.now(timezone.utc)

        organization = Organization.objects.all().create(name="test", country="NL", created_on=now, is_dead=False)
        organization.layers.add(organization_type)

        url = Url.objects.all().create(url="test.nl", created_on=now, is_dead=False, not_resolvable=False)

        # create the n-n connection between url and organization
        url.organization.add(organization)
        url.save()

        endpoint = Endpoint.objects.create(url=url, port=443, protocol="https")

        EndpointGenericScan.objects.create(
            endpoint=endpoint,
            evidence="evidence",
            type="tls_qualys_encryption_quality",
            rating_determined_on=now,
            is_the_latest_scan=True,
            rating="F",
            comply_or_explain_is_explained=True,
            comply_or_explain_explained_by="test",
            comply_or_explain_explained_on=now,
            comply_or_explain_explanation_valid_until=now,
        )

        UrlGenericScan.objects.create(
            url=url,
            evidence="evidence",
            type="tls_qualys_encryption_quality",
            rating_determined_on=now,
            is_the_latest_scan=True,
            rating="F",
            comply_or_explain_is_explained=True,
            comply_or_explain_explained_by="test",
            comply_or_explain_explained_on=now,
            comply_or_explain_explanation_valid_until=now,
        )

    recent_explains = get_recent_explains("NL", "municipality")

    del recent_explains[0]["organizations"]
    del recent_explains[1]["organizations"]

    assert recent_explains == [
        {
            "explained_by": "test",
            "explained_on": "2022-01-24T00:00:00+00:00",
            "explanation": "",
            "original_explanation": "Broken Transport Security, rated F",
            "original_severity": "high",
            "scan_type": "tls_qualys_encryption_quality",
            "subject": "test.nl",
            "valid_until": "2022-01-24T00:00:00+00:00",
        },
        {
            "explained_by": "test",
            "explained_on": "2022-01-24T00:00:00+00:00",
            "explanation": "",
            "original_explanation": "Broken Transport Security, rated F",
            "original_severity": "high",
            "scan_type": "tls_qualys_encryption_quality",
            "subject": "test.nl - https/443 - IPv4",
            "valid_until": "2022-01-24T00:00:00+00:00",
        },
    ]
