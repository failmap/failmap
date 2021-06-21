from datetime import timedelta
from typing import Any, Dict, Union

from django.db.models import Count, Q
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan


def get_recent_explains(country, organization_type):
    """
    Because explains are possible on every scan type, try to get 10 of each, merge them and orders them chronologically.
    It's not the nicest solution as urlscan might nog be as used as endpointgenericscan.
    :return:
    """

    return get_all_explains(country, organization_type, limit=50)


def get_all_explains(country, organization_type, limit=0):

    limit = 999999 if limit == 0 else limit

    country = get_country(country)
    organization_type = get_organization_type(organization_type)

    # some urls are used by a lot of organizations, we only need the distinct explanation, and
    # the organizations will be matched later.
    # https://stackoverflow.com/questions/30752268/how-to-filter-objects-for-count-annotation-in-django

    # we're currently not taking into account what endpoint, URL's and organizations are alive at a certain point.
    # in that sense we're not taking history in account... Only what is relevant _NOW_
    # This should change, adding some nice complex Q conditions for checking a certain date.
    # something like: & (  Q(url__organization__is_dead=False, created_on__lte=some_date)
    #                    | Q(is_dead=True,  created_on__lte=some_date, is_dead_since__gte=some_date)
    #
    #                 & (  Q(is_dead=False, created_on__lte=some_date)
    #                    | Q(is_dead=True,  created_on__lte=some_date, is_dead_since__gte=some_date)
    ugss = (
        UrlGenericScan.objects.all()
        .filter(
            comply_or_explain_is_explained=True,
            is_the_latest_scan=True,
        )
        .annotate(
            n_urls=Count(
                "url",
                filter=Q(
                    url__organization__is_dead=False,
                    url__organization__country=country,
                    url__organization__type_id=organization_type,
                    url__is_dead=False,
                    url__not_resolvable=False,
                ),
            )
        )
        .filter(n_urls=1)
        .order_by("-comply_or_explain_explained_on")[0:limit]
    )

    egss = (
        EndpointGenericScan.objects.all()
        .filter(
            comply_or_explain_is_explained=True,
            is_the_latest_scan=True,
        )
        .annotate(
            n_urls=Count(
                "endpoint",
                filter=Q(
                    endpoint__is_dead=False,
                    endpoint__url__not_resolvable=False,
                    endpoint__url__is_dead=False,
                    endpoint__url__organization__is_dead=False,
                    endpoint__url__organization__country=country,
                    endpoint__url__organization__type_id=organization_type,
                ),
            )
        )
        .filter(n_urls__gte=1)
        .order_by("-comply_or_explain_explained_on")[0:limit]
    )

    explains = []

    for scan in ugss:
        explains.append(get_explanation("url", scan))

    for scan in egss:
        explains.append(get_explanation("endpoint", scan))

    # sorting
    explains = sorted(explains, key=lambda k: (k["explained_on"]), reverse=True)

    return explains


def get_explanation(type, scan):
    calculation = get_severity(scan)

    now = timezone.now().isoformat()
    explained_on = scan.comply_or_explain_explained_on.isoformat() if scan.comply_or_explain_explained_on else now

    this_explain = {
        "scan_type": scan.type,
        "explanation": scan.comply_or_explain_explanation,
        "explained_by": scan.comply_or_explain_explained_by,
        "explained_on": explained_on,
        "valid_until": scan.comply_or_explain_explanation_valid_until.isoformat(),
        "original_severity": "high" if calculation["high"] else "medium" if calculation["medium"] else "low",
        "original_explanation": calculation["explanation"],
    }

    if type == "url":
        this_explain["organizations"] = scan.url.organization.name
        this_explain["subject"] = str(scan.url.url)

    if type == "endpoint":
        this_explain["organizations"] = list(scan.endpoint.url.organization.all().values("id", "name"))
        this_explain["subject"] = str("%s - %s/%s - IPv%s") % (
            scan.endpoint.url,
            scan.endpoint.protocol,
            scan.endpoint.port,
            scan.endpoint.ip_version,
        )

    return this_explain


def get_scan(scan_id: int, scan_type: str) -> Union[EndpointGenericScan, UrlGenericScan, None]:

    if scan_type in ENDPOINT_SCAN_TYPES:
        return EndpointGenericScan.objects.all().filter(pk=scan_id, type=scan_type, is_the_latest_scan=True).first()

    if scan_type in URL_SCAN_TYPES:
        return UrlGenericScan.objects.all().filter(pk=scan_id, type=scan_type, is_the_latest_scan=True).first()

    return None


def explain(scan_id: int, scan_type: str, explanation: str, explained_by: str, days: int = 365) -> Dict[str, Any]:

    scan = get_scan(scan_id, scan_type)
    if not scan:
        return {
            "error": True,
            "success": False,
            "message": "Could not find scan. It's only possible to add " "explanations to the latest scan.",
        }

    if not explanation:
        return {"error": True, "success": False, "message": "Explanation was empty, could not save explanation."}

    # you can change the explanation at zero cost. It won't extend the expiration date, etc.
    if scan.comply_or_explain_is_explained is True:
        scan.comply_or_explain_explanation = explanation
        scan.save()
        return {"error": False, "success": True, "message": "Explanation altered."}

    scan.comply_or_explain_is_explained = True
    scan.comply_or_explain_explained_by = explained_by
    scan.comply_or_explain_explained_on = timezone.now()
    scan.comply_or_explain_explanation_valid_until = timezone.now() + timedelta(days=int(days))
    scan.comply_or_explain_explanation = explanation
    scan.comply_or_explain_case_handled_by = "Logged in user..."
    scan.save()

    return {"error": False, "success": True, "message": "Explanation saved. This will be included in the next report."}


def remove_explanation(scan_id: int, scan_type: str) -> Dict[str, Any]:
    # this is free

    scan = get_scan(scan_id, scan_type)
    if not scan:
        return {"success": False, "error": True, "message": "This is not a valid scan. Is it the last scan?"}

    scan.comply_or_explain_is_explained = False
    scan.save(update_fields=["comply_or_explain_is_explained"])
    return {
        "success": True,
        "error": False,
        "message": "Explanation removed. " "This will be included in the next report.",
    }
