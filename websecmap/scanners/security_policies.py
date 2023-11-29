# Endpoint scanner to determine different roles per endpoint based on standard it configuration / heuristics.
# This will make it easier to target certain scanners to only relevant endpoint.
# This also defines the standard IT landscape a little bit
from typing import List

from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.models import Endpoint, SecurityPolicy, EndpointGenericScan
from datetime import datetime, timezone, timedelta


@app.task(queue="database")
def apply_all_security_policies():
    for policy in SecurityPolicy.objects.all():
        apply_security_policy(policy)


@app.task(queue="database")
def apply_all_affects():
    for policy in SecurityPolicy.objects.all():
        apply_affects(policy)


def check_policy_sanity(policy: SecurityPolicy) -> bool:
    return any(
        [
            policy.common_subdomains,
            policy.common_ports,
            policy.common_ip_versions,
            policy.common_protocols,
            policy.common_html_front_page_content,
            policy.common_header_names,
            policy.common_layers,
        ]
    )


def filter_policy_endpoints(policy: SecurityPolicy) -> List[Endpoint]:
    if not check_policy_sanity(policy):
        return []

    # returns a queryset of endpoints, never return dead stuff as that is not presented anywhere
    endpoints_in_policy = Endpoint.objects.all().filter(is_dead=False, url__is_dead=False, url__not_resolvable=False)

    if policy.common_ports:
        endpoints_in_policy = endpoints_in_policy.filter(port__in=policy.common_ports)

    if policy.common_ip_versions:
        endpoints_in_policy = endpoints_in_policy.filter(ip_version__in=policy.common_ip_versions)

    if policy.common_protocols:
        endpoints_in_policy = endpoints_in_policy.filter(protocol__in=policy.common_protocols)

    if policy.common_subdomains:
        endpoints_in_policy = endpoints_in_policy.filter(url__computed_subdomain__in=policy.common_subdomains)

    if policy.common_html_front_page_content:
        endpoints_in_policy = endpoints_in_policy.filter(
            httpendpointcontent__content__contains=policy.common_html_front_page_content,
            httpendpointcontent__path="/",
            httpendpointcontent__is_the_latest=True,
        )

    if policy.common_header_names:
        endpoints_in_policy = endpoints_in_policy.filter(
            # all keys, inclusive, so all keys have to be present(!)
            httpendpointheaders__header_names__has_keys=policy.common_header_names,
            httpendpointheaders__is_the_latest=True,
        )

    if policy.common_layers:
        endpoints_in_policy = endpoints_in_policy.filter(
            url__organization__layers__name__in=policy.common_layers,
        )

    eps = list(endpoints_in_policy)
    log.debug("Found %s endpoints in policy", len(eps))
    return eps


def apply_security_policy(policy: SecurityPolicy):
    for endpoint in filter_policy_endpoints(policy):
        endpoint.security_policies.add(policy)


def remove_security_policy(policy: SecurityPolicy):
    for endpoint in filter_policy_endpoints(policy):
        endpoint.security_policies.remove(policy)


def add_policy_by_name(endpoint_id: int, policy_name: str) -> None:
    # upgrade "webserver" to "webserver_json" or "webserver_xml" so you know there is no website there...
    endpoint = Endpoint.objects.filter(pk=endpoint_id).only("id", "security_policies").first()
    if not endpoint:
        return

    if policy_name in endpoint.security_policies_list:
        return

    policy, _ = SecurityPolicy.objects.get_or_create(technical_policy_name=policy_name)
    endpoint.security_policies.add(policy)


def apply_affects(policy: SecurityPolicy) -> int:
    # see if it has a scan according to affect_explain_scoring_policy, if so, explain it.
    return sum(
        add_policy_exemption_explanation(
            scan=epgs,
            explanation=f"policy_explanation_fits_{policy.technical_policy_name}",
            duration=timedelta(days=1000),
        )
        for epgs in get_affected_epgs(policy)
    )


def remove_affects(policy: SecurityPolicy) -> int:
    return sum(
        remove_policy_exemption_explanation(
            scan=epgs,
            explanation=f"policy_explanation_fits_{policy.technical_policy_name}",
        )
        for epgs in get_affected_epgs(policy)
    )


def get_affected_epgs(policy: SecurityPolicy) -> List[EndpointGenericScan]:
    returned_epgs = []
    for affect in policy.affect_explain_scoring_policy.all():
        log.debug("Looking at affect %s", affect)
        for endpoint in Endpoint.objects.all().filter(
            # don't touch dead stuff:
            security_policies=policy,
            is_dead=False,
            url__is_dead=False,
            url__not_resolvable=False,
        ):
            log.debug("Looking at endpoint %s", endpoint)
            returned_epgs.extend(
                iter(
                    EndpointGenericScan.objects.all().filter(
                        endpoint=endpoint,
                        is_the_latest_scan=True,
                        type=affect.scan_type,
                        rating=affect.conclusion,
                    )
                )
            )
    log.debug("Found %d affected endpoints", len(returned_epgs))
    return returned_epgs


def remove_policy_exemption_explanation(scan: EndpointGenericScan, explanation: str) -> bool:
    # only exactly matching explanations can be undone
    if any(
        [
            scan.comply_or_explain_is_explained,
            scan.comply_or_explain_case_handled_by != "WebSecMap Policy Bot",
            scan.comply_or_explain_explained_by != "WebSecMap Policy Bot",
            scan.explanation != explanation,
        ]
    ):
        return False

    log.debug("Removing exemption explanation %s on scan %s", explanation, scan)

    scan.comply_or_explain_is_explained = False
    scan.comply_or_explain_case_handled_by = ""
    scan.comply_or_explain_explained_by = ""
    scan.comply_or_explain_explanation = ""
    scan.comply_or_explain_explained_on = None
    scan.comply_or_explain_explanation_valid_until = None
    scan.save()
    return True


def add_policy_exemption_explanation(scan: EndpointGenericScan, explanation: str, duration: timedelta) -> bool:
    if scan.comply_or_explain_is_explained:
        return False

    log.debug("Adding exemption explanation %s on scan %s", explanation, scan)

    scan.comply_or_explain_is_explained = True
    scan.comply_or_explain_case_handled_by = "WebSecMap Policy Bot"
    scan.comply_or_explain_explained_by = "Websecmap Policy Bot"
    scan.comply_or_explain_explanation = explanation
    scan.comply_or_explain_explained_on = datetime.now(timezone.utc)
    scan.comply_or_explain_explanation_valid_until = datetime.now(timezone.utc) + duration
    scan.save()

    return True
