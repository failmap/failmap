import logging
import ssl
from datetime import datetime, timedelta
from typing import List

from celery import group
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID
from django.db.models import Q

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation, get_latest_endpoint_scan
from websecmap.scanners.models import EndpointGenericScan, Endpoint
from websecmap.scanners.scanner import unique_and_random

log = logging.getLogger(__package__)

SCANNER = "autoexplain_trust_microsoft"

applicable_subdomains = {
    "lyncdiscover": ["*.online.lync.com", "meet.lync.com", "*.infra.lync.com", "sched.lync.com", "*.lync.com"],
    "sip": ["sipfed.online.lync.com", "*.online.lync.com", "*.infra.lync.com", "*.lync.com"],
    "enterpriseenrollment": [
        "manage.microsoft.com",
        "admin.manage.microsoft.com",
        "EnterpriseEnrollment-s.manage.microsoft.com",
        "r.manage.microsoft.com",
        "p.manage.microsoft.com",
        "i.manage.microsoft.com",
        "a.manage.microsoft.com",
    ],
    "enterpriseregistration": ["*.enterpriseregistration.windows.net", "enterpriseregistration.windows.net"],
    "msoid": [
        "*.accesscontrol.windows.net",
        "*.accesscontrol.windows-ppe.net",
        "*.b2clogin.com",
        "*.cpim.windows.net",
        "*.microsoftaik.azure.net",
        "*.microsoftaik-int.azure-int.net",
        "*.windows-ppe.net",
        "aadg.windows.net",
        "aadgv6.ppe.windows.net",
        "aadgv6.windows.net",
        "account.live.com",
        "account.live-int.com",
        "api.password.ccsctp.com",
        "api.passwordreset.microsoftonline.com",
        "autologon.microsoftazuread-sso.com",
        "becws.ccsctp.com",
        "clientconfig.microsoftonline-p.net",
        "clientconfig.microsoftonline-p-int.net",
        "companymanager.ccsctp.com",
        "companymanager.microsoftonline.com",
        "cpim.windows.net",
        "device.login.microsoftonline.com",
        "device.login.windows-ppe.net",
        "directoryproxy.ppe.windows.net",
        "directoryproxy.windows.net",
        "graph.ppe.windows.net",
        "graph.windows.net",
        "graphstore.windows.net",
        "login.live.com",
        "login.live-int.com",
        "login.microsoft.com",
        "login.microsoftonline.com",
        "login.microsoftonline-p.com",
        "login.microsoftonline-pst.com",
        "login.microsoft-ppe.com",
        "login.windows.net",
        "logincert.microsoftonline.com",
        "logincert.microsoftonline-int.com",
        "login-us.microsoftonline.com",
        "microsoftaik.azure.net",
        "microsoftaik-int.azure-int.net",
        "nexus.microsoftonline-p.com",
        "nexus.microsoftonline-p-int.com",
        "pas.windows.net",
        "pas.windows-ppe.net",
        "password.ccsctp.com",
        "passwordreset.activedirectory.windowsazure.us",
        "passwordreset.microsoftonline.com",
        "provisioning.microsoftonline.com",
        "signup.live.com",
        "signup.live-int.com",
        "sts.windows.net",
        "xml.login.live.com",
        "xml.login.live-int.com",
        "*.login.microsoftonline.com",
        "login.microsoftonline-int.com",
        "accesscontrol.aadtst3.windows-int.net",
        "*.accesscontrol.aadtst3.windows-int.net",
        "api.login.microsoftonline.com",
        "*.r.login.microsoftonline.com",
        "*.r.login.microsoft.com",
        "*.login.microsoft.com",
    ],
}


@app.task(queue="storage")
def plan_scan():
    scans = EndpointGenericScan.objects.all().filter(
        endpoint__url__in=get_relevant_microsoft_domains_from_database(),
        type="tls_qualys_certificate_trusted",
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        endpoint__protocol="https",
        endpoint__is_dead=False,
        rating="not trusted",
    )

    urls = [scan.endpoint.url.pk for scan in scans]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):
    """
    Adds explanations to microsoft specific infrastructure, which in itself is secure, but will be reported as being
    not trusted. These are limited to a set of subdomains and a specific test.

    We _really_ do not like exceptions like these, yet, trust is managed per device. And if the device is configured
    for a certain domain: it is trusted internally, which is good enough for us.

    This infra is used a lot by the dutch government, so instead of managing hundreds of exceptions by hand.
    """

    # Only check this on the latest scans, do not alter existing explanations
    scans = (
        EndpointGenericScan.objects.all()
        .filter(
            endpoint__url__in=urls,
            type="tls_qualys_certificate_trusted",
            is_the_latest_scan=True,
            comply_or_explain_is_explained=False,
            endpoint__protocol="https",
            endpoint__is_dead=False,
            rating="not trusted",
        )
        .only("id")
    )

    tasks = [
        scan.si(scan_id=scan) | plannedscan.finish.si("scan", SCANNER, scan.endpoint.url.pk)
        for scan in list(set(scans))
    ]

    return group(tasks)


# todo: this needs to be split out onto several workers, now it can hinder the storage queue.
@app.task(queue="storage")
def scan(scan_id):

    scan = EndpointGenericScan.objects.all().filter(id=scan_id)
    if not scan:
        return

    certificate = retrieve_certificate(url=scan.endpoint.url.url, port=scan.endpoint.port)

    matches_exception_policy = certificate_matches_microsoft_exception_policy(
        certificate, scan, applicable_subdomains, trusted_organization="Microsoft Corporation"
    )

    if not matches_exception_policy:
        return

    # when all checks pass, and indeed the SSL_ERROR_BAD_CERT_DOMAIN was found, the finding is explained
    log.debug(f"Scan {scan} fits all criteria to be auto explained for incorrect cert usage.")
    add_bot_explanation(scan, "trusted_on_local_device_with_custom_trust_policy", timedelta(days=365 * 10))
    autoexplain_trust_microsoft_and_include_their_webserver_headers(scan)


def get_relevant_microsoft_domains_from_database() -> List[Url]:
    # Warning: only returns the url id inside the url object due to optimization.

    # Fix #294: A subdomain can be sub-sub-sub domain. So perform a few more queries and get be sure that
    # all subdomains are accounted for.
    possible_urls = []
    for subdomain in applicable_subdomains.keys():
        possible_urls += list(
            Url.objects.all()
            .filter(Q(computed_subdomain__startswith=f"{subdomain}.") | Q(computed_subdomain=f"{subdomain}"))
            .filter(is_dead=False, not_resolvable=False)
            .only("id")
        )

    return possible_urls


def retrieve_certificate(url: str, port: int = 443) -> [x509.Certificate, None]:
    try:
        pem_data = ssl.get_server_certificate((url, port))
    except Exception:
        # One gazillion network errors and transmission issues can occur here.
        return

    # load_pem_x509_certificate takes bytes, not string. Vague error happens otherwise, IDE does not type check here.
    return x509.load_pem_x509_certificate(pem_data.encode(), default_backend())


def certificate_matches_microsoft_exception_policy(
    certificate: x509.Certificate, scan, applicable_subdomains, trusted_organization
) -> bool:
    """
    It's possible to fake all checks with a self signed certificate. The reason we _still_ do it like this, is that
    it will be mean headlines when a government organization issues self signed certificates in the name of Microsoft.
    That would be just too funny. It's possible to check the entire trust chain with cert_chain_resolver and similar
    tools. At the moment news headlines outvalue better checks :)

    :param certificate:
    :param scan:
    :param applicable_subdomains:
    :param trusted_organization:
    :return:
    """
    if not certificate:
        log.debug(f"Could not retrieve certificate for {scan.endpoint.url.url}.")
        return False

    if certificate.not_valid_before > datetime.now():
        log.debug(
            f"Certificate for {scan.endpoint.url.url} is not valid before {certificate.not_valid_before}. "
            f"Not trusted."
        )
        return False

    if datetime.now() > certificate.not_valid_after:
        log.debug(f"Certificate for {scan.endpoint.url.url} has expired  {certificate.not_valid_after}. Not trusted.")
        return False

    # Likely subdomain:
    # lyncdiscover.site.example.com
    # lyncdiscover.example.com
    if "." in scan.endpoint.url.computed_subdomain:
        fragments = scan.endpoint.url.computed_subdomain.split(".")
        microsoft_service = fragments[0]
    else:
        microsoft_service = scan.endpoint.url.computed_subdomain

    # check if the issuer matches
    # <Name(C=US,ST=Washington,L=Redmond,O=Microsoft Corporation,OU=Microsoft IT,CN=Microsoft IT TLS CA 5)>
    _names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    names = [name.value for name in _names]
    if names[0] not in applicable_subdomains[microsoft_service]:
        log.debug(f"Certificate for {scan.endpoint.url.url} not in accepted names, value: {names}. Not trusted.")
        return False

    # check if the common name or alt name of the certificate matches the subdomain
    _names = certificate.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    names = [name.value for name in _names]
    if trusted_organization not in names:
        log.debug(
            f"Certificate for {scan.endpoint.url.url} not handed out by {trusted_organization} but by "
            f"{names}. Not trusted."
        )
        return False

    return True


def autoexplain_trust_microsoft_and_include_their_webserver_headers(scan):
    # Find a neighboring http endpoint, also there the headers are not relevant as the same security
    # protocol is used. DNS can only switch on addresses and ip-versions. But not protocol and port.
    http_endpoint = Endpoint.objects.all().filter(
        # We don't care about what port is applied here.
        protocol="http",
        ip_version=scan.endpoint.ip_version,
        url=scan.endpoint.url,
        is_dead=False,
        url__is_dead=False,
        url__not_resolvable=False,
    )
    relevant_endpoints = list(set(http_endpoint))

    for endpoint in relevant_endpoints + [scan.endpoint]:

        intended_for_devices = "service_intended_for_devices_not_browsers"

        # Also retrieve all http security headers, they are never correct. The only thing that is actually
        # tested is the encryption quality here.
        header_scans = [
            "http_security_header_strict_transport_security",
            "http_security_header_x_content_type_options",
            "http_security_header_x_frame_options",
            "http_security_header_x_xss_protection",
        ]
        for header_scan in header_scans:
            latest_scan = get_latest_endpoint_scan(endpoint=endpoint, scan_type=header_scan)
            if not latest_scan:
                continue

            if not latest_scan.comply_or_explain_explanation == intended_for_devices:
                add_bot_explanation(latest_scan, intended_for_devices, timedelta(days=365 * 10))
