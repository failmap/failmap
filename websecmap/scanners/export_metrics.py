from websecmap.scanners.models import EndpointGenericScan
import json


def export_current_metrics(
    layer: str = "central_government",
    scan_type: str = "web_privacy_cookies",
    rating: str = "web_privacy_cookies_neutral",
):
    epgs = EndpointGenericScan.objects.all().filter(
        is_the_latest_scan=True,
        endpoint__url__organization__layers__name=layer,
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        rating=rating,
        type=scan_type,
    )
    data = []
    for epg in epgs:
        record = {
            "endpoint": str(epg.endpoint),
            "url": str(epg.endpoint.url),
            "endpoint_id": epg.endpoint.id,
            "url_id": epg.endpoint.url.id,
            "rating": epg.rating,
            "type": epg.type,
            # 'layer': epg.endpoint.url.organization.layers.name,
            "evidence": epg.evidence,
        }
        data.append(record)
    print(json.dumps(data, indent=4))
