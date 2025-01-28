import json
from io import StringIO
from typing import List

from django.core.management import call_command

from websecmap.map.models import Configuration
from websecmap.organizations.models import (
    AlternativeName,
    Coordinate,
    Organization,
    OrganizationSurrogateId,
    OrganizationType,
    Url,
    UrlWhois,
)
from websecmap.scanners.models import (
    Cookie,
    CookieBanner,
    CookieBannerAttribute,
    CookieScanSession,
    Endpoint,
    EndpointGenericScan,
    ExternalResource,
    HttpEndpointHeaders,
    Screenshot,
    UrlGenericScan,
    UrlIp,
)


def create_organization_development_fixture(relevant_organization_ids: List[int]) -> str:
    # make sure to get a list of all the existing organizations, this saves looping to individual queries and thus
    # makes the export much faster.
    existing_organizations = (
        Organization.objects.all().filter(id__in=relevant_organization_ids).only("id").values_list("id", flat=True)
    )

    fixture = []
    if not existing_organizations:
        return json.dumps(fixture)

    exports = [
        # generic stuff, all directly related where the organization is the child
        [Configuration, {"organization_type__organization_on_layer__in": existing_organizations}],
        [OrganizationType, {"organization_on_layer__in": existing_organizations}],
        # stuff related to the organization as a parent
        [Organization, {"id__in": existing_organizations}],
        [Url, {"organization__id__in": existing_organizations}],
        [Coordinate, {"organization__id__in": existing_organizations}],
        [AlternativeName, {"organization__id__in": existing_organizations}],
        [OrganizationSurrogateId, {"organization__id__in": existing_organizations}],
        [UrlWhois, {"url__organization__id__in": existing_organizations}],
        # scanning
        [UrlIp, {"url__organization__id__in": existing_organizations}],
        [UrlGenericScan, {"url__organization__id__in": existing_organizations}],
        [Endpoint, {"url__organization__id__in": existing_organizations}],
        [EndpointGenericScan, {"endpoint__url__organization__id__in": existing_organizations}],
        [HttpEndpointHeaders, {"endpoint__url__organization__id__in": existing_organizations}],
        # skipped as it creates a lot of wasteful data
        # [HttpEndpointContent, {'endpoint__url__organization__id__in': existing_organizations}],
        [Screenshot, {"endpoint__url__organization__id__in": existing_organizations}],
        [CookieScanSession, {"endpoint__url__organization__id__in": existing_organizations}],
        [Cookie, {"endpoint__url__organization__id__in": existing_organizations}],
        [CookieBanner, {"endpoint__url__organization__id__in": existing_organizations}],
        [CookieBannerAttribute, {"cookiebanner__endpoint__url__organization__id__in": existing_organizations}],
        [ExternalResource, {"endpoint__url__organization__id__in": existing_organizations}],
        # we can omit plannedscan, it's a lot of wasteful data
    ]

    for model, model_filter in exports:
        fixture.extend(fixturize(model, **model_filter))

    return json.dumps(fixture)


def fixturize(model, **kwargs):
    app_label = model._meta.app_label
    ids = model.objects.all().filter(**kwargs).only("id").values_list("id", flat=True)
    data = get_fixture(f"{app_label}.{model._meta.model_name}", ids)
    return json.loads(data)


def get_fixture(label: str, pks: List[int]) -> str:
    # based upon https://stackoverflow.com/questions/1113096/django-dump-data-for-a-single-model
    args = ["dumpdata", "--natural-foreign", "--natural-primary", label]
    with StringIO() as buffer:
        call_command(*args, pks=",".join([str(pk) for pk in pks]), stdout=buffer)
        data = buffer.getvalue()
    return data
