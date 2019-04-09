from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.reporting.severity import get_severity
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan


def get_recent_explains(country, organization_type):
    """
    Because explains are possible on every scan type, try to get 10 of each, merge them and orders them chronologically.
    It's not the nicest solution as urlscan might nog be as used as endpointgenericscan.
    :return:
    """

    return get_all_explains(country, organization_type, limit=10)


def get_all_explains(country, organization_type, limit=0):

    limit = 999999 if limit == 0 else limit

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    ugss = UrlGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                               url__organization__country=country,
                                               url__organization__type_id=organization_type
                                               ).order_by('comply_or_explain_explained_on')[0:limit]
    egss = EndpointGenericScan.objects.all().filter(comply_or_explain_is_explained=True,
                                                    endpoint__url__organization__country=country,
                                                    endpoint__url__organization__type_id=organization_type
                                                    ).order_by('comply_or_explain_explained_on')[0:limit]

    explains = []

    for scan in ugss:
        explains.append(get_explanation('url', scan))

    for scan in egss:
        explains.append(get_explanation('endpoint', scan))

    # sorting
    explains = sorted(explains, key=lambda k: (k['explained_on']), reverse=True)

    return explains


def get_explanation(type, scan):
    calculation = get_severity(scan)

    explain = {
        'organizations': scan.url.organization.name if type == "url" else list(
            scan.endpoint.url.organization.all().values('id', 'name')),
        'scan_type': scan.type,
        'explanation': scan.comply_or_explain_explanation,
        'explained_by': scan.comply_or_explain_explained_by,
        'explained_on': scan.comply_or_explain_explained_on.isoformat(
        ) if scan.comply_or_explain_explained_on else timezone.now().isoformat(),
        'valid_until': scan.comply_or_explain_explanation_valid_until.isoformat(),
        'original_severity': "high" if calculation['high'] else "medium" if calculation['medium'] else "low",
        'original_explanation': calculation['explanation'],
        'subject': str("%s %s/%s on IPv%s") % (
            scan.endpoint.url, scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version
        ) if type == "endpoint" else str(scan.url.url)
    }

    return explain
