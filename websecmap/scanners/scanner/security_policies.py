# Endpoint scanner to determine different roles per endpoint based on standard it configuration / heuristics.
# This will make it easier to target certain scanners to only relevant endpoint.
# This also defines the standard IT landscape a little bit
from websecmap.app import log
from websecmap.celery import app
from websecmap.scanners.models import Endpoint


@app.task(queue="storage")
def initialize_security_policies(force: bool = False):
    # Set up roles for endpoints so a certain policy can be applied to them. There are only so many setups
    # that are sane and acceptable.
    for endpoint in Endpoint.objects.all():
        determine_security_policy(endpoint, force)


def determine_security_policy(endpoint: Endpoint, force: bool = False):

    if endpoint.security_policies.count() > 0 and not force:
        log.debug("Endpoint already has a role")
        return

    determine_http_https_policy(endpoint)
    determine_ftp_policy(endpoint)


def determine_http_https_policy(endpoint: Endpoint):
    # https is not just https websites but also a lot of other things that might / might not be recognized
    # by tools such as nmap.
    # beware: this is not protocol analysis but security policy analysis.
    # It's not possible to have 'mail' and then https/443: then its probably webmail and not smtp.
    port = endpoint.port
    webserver_ports = [443, 80, 8088, 8080, 8443]

    if port not in webserver_ports:
        return

    if endpoint.protocol not in ["http", "https"]:
        return

    # default role:
    if not endpoint.security_policies_list:
        add_security_policy(endpoint, "webserver")

    subdomain = endpoint.url.computed_subdomain
    if not subdomain:
        return

    # heuristics based on their name, it might be wrong and still be a website, which should be determined
    # another way
    if subdomain in ["pki", "crl"]:
        reset_security_policies(endpoint, "certificate_revocation_list")

    # todo: then this _should not_ have a website on that port or we should not be able to connect...
    if "vpn" in subdomain or subdomain in ["telewerken", "thuiswerken", "extranet", "intranet"]:
        reset_security_policies(endpoint, "vpn")

    if "voip" in subdomain or subdomain in ["sip"]:
        reset_security_policies(endpoint, "voip")

    if subdomain in ["autodiscover"]:
        reset_security_policies(endpoint, "ms_autodiscover")


def determine_ftp_policy(endpoint: Endpoint):
    port = endpoint.port
    if port == 21:
        add_security_policy(endpoint, "file_transfer")


def reset_security_policies(endpoint: Endpoint, role: str):
    clear_security_policies(endpoint)
    add_security_policy(endpoint, role)


def clear_security_policies(endpoint: Endpoint):
    endpoint.security_policies.clear()


def add_security_policy(endpoint: Endpoint, role: str):
    endpoint.security_policies.add(role)


def further_specify_security_policy(endpoint_id: int, current_role: str, specific_role: str) -> None:
    # upgrade "webserver" to "webserver_json" or "webserver_xml" so you know there is no website there...
    endpoint = Endpoint.objects.filter(pk=endpoint_id).first()
    if not endpoint:
        return

    if endpoint.security_policies_list != [current_role]:
        log.debug("Role already too specific")
        return

    reset_security_policies(endpoint, f"{current_role}_{specific_role}")
