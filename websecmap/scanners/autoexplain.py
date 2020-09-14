"""
These automated explanations match standardardized IT infrastructure. For all other comply or explain actions, use
the management interface to quickly add explanations.

The approach here is as-strict-as-possible whitelisting. This means for example that while a certain error is accepted,
other errors such as certificate expiration, mis configurations and such will still be seen as insufficient.

Local, non-vendor policies are not taken into account: they should standardize and try to comply first.
"""

import logging
import ssl
from datetime import datetime, timedelta

import pytz
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import EndpointGenericScan
import dns

log = logging.getLogger(__package__)


@app.task(queue="storage")
def autoexplain():
    """
    Collective method to run various autoexplain scripts. Used to keep the call to these methods consistent when
    more autoexplains are added.
    :return:
    """

    autoexplain_trust_microsoft()
    autoexplain_no_https_microsoft()


def autoexplain_no_https_microsoft():
    """
    Microsoft Office365/Exchange need the autodiscover subdomain. This is configured as a CNAME. The CNAME
    cannot be further configured. Microsoft does not expose an HTTPS service over this subdomain, only http.
    This is true for the "online" configuration, not for the "on premise" configuration.
    The documentation on "WHY IS THIS SECURE" is not really well done (or at least microsoft style obfuscated).
    Currently we "assume" that they know what they are doing, since they have a well performing security team.
    issue: https://gitlab.com/internet-cleanup-foundation/web-security-map/-/issues/271

    The CNAME will point to autodiscover.outlook.com. Thus in that case we can quickly validate that this specific
    issue will always be the same.
    """

    scan_type = "plain_https"
    possible_urls = Url.objects.all().filter(computed_subdomain="autodiscover")

    log.debug(f"Found {len(possible_urls)} possible autodiscover urls.")

    # Only check this on the latest scans, do not alter existing explanations
    scans = EndpointGenericScan.objects.all().filter(
        endpoint__url__in=possible_urls,
        type=scan_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        endpoint__protocol="http",
        endpoint__port=80,
        # it DOES redirect to a secure site.
        rating="25",
    )

    log.debug(f"Found {len(scans)} possible autodiscover subdomains. Checking them for automatic explanation.")

    for scan in scans:
        try:
            result = dns.resolver.query(scan.endpoint.url.url, "CNAME")
            for cnameval in result:
                # don't accept trickery such as autodiscover.outlook.com.mydomain.com.
                log.debug(f"Retrieved cname value: {cnameval}.")
                if "autodiscover.outlook.com." == str(cnameval):
                    log.debug("Perfect match, will add automatic explanation.")
                    add_bot_explanation(scan, "service_intentionally_designed_this_way", timedelta(days=365 * 10))
        except dns.exception.DNSException as e:
            log.debug(f"Received an expectable error from dns server: {e}.")
            # can happen of course.
            # sample: dns.resolver.NXDOMAIN, dns.exception.Timeout, dns.resolver.NoAnswer, dns.query.BadResponse


def autoexplain_trust_microsoft():
    """
    Adds explanations to microsoft specific infrastructure, which in itself is secure, but will be reported as being
    not trusted. These are limited to a set of subdomains and a specific test.

    We _really_ do not like exceptions like these, yet, trust is managed per device. And if the device is configured
    for a certain domain: it is trusted internally, which is good enough for us.

    This infra is used a lot by the dutch government, so instead of managing hundreds of exceptions by hand.
    :return:
    """

    scan_type = "tls_qualys_certificate_trusted"
    trusted_organization = "Microsoft Corporation"
    # accepted_issue = 'SSL_ERROR_BAD_CERT_DOMAIN'
    standard_explanation = "trusted_on_local_device_with_custom_trust_policy"
    intended_for_devices = "service_intended_for_devices_not_browsers"
    explanation_duration = timedelta(days=365 * 10)

    applicable_subdomains = {
        "lyncdiscover": ["*.online.lync.com", "meet.lync.com", "*.infra.lync.com", "sched.lync.com", "*.lync.com"],
        "sip": ["sipfed.online.lync.com", "*.online.lync.com", "*.infra.lync.com", "*.lync.com"],
        "enterpriseenrollment": [
            "manage.microsoft.com",
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

    possible_urls = Url.objects.all().filter(computed_subdomain__in=applicable_subdomains.keys())

    # Only check this on the latest scans, do not alter existing explanations
    scans = EndpointGenericScan.objects.all().filter(
        endpoint__url__in=possible_urls,
        type=scan_type,
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        endpoint__protocol="https",
        rating="not trusted",
    )

    scans = list(set(scans))
    for scan in scans:
        certificate = retrieve_certificate(url=scan.endpoint.url.url, port=scan.endpoint.port)

        matches_exception_policy = certificate_matches_microsoft_exception_policy(
            certificate, scan, applicable_subdomains, trusted_organization
        )

        if matches_exception_policy:
            # when all checks pass, and indeed the SSL_ERROR_BAD_CERT_DOMAIN was found, the finding is explained
            log.debug(f"Scan {scan} fits all criteria to be auto explained for incorrect cert usage.")
            add_bot_explanation(scan, standard_explanation, explanation_duration)

            # Also retrieve all http security headers, they are never correct. The only thing that is actually
            # tested is the encryption quality here.
            header_scans = [
                "http_security_header_strict_transport_security",
                "http_security_header_x_content_type_options",
                "http_security_header_x_frame_options",
                "http_security_header_x_xss_protection",
            ]
            for header_scan in header_scans:
                latest_scan = get_latest_endpoint_scan(endpoint=scan.endpoint, scan_type=header_scan)
                if latest_scan:
                    add_bot_explanation(latest_scan, intended_for_devices, explanation_duration)


def get_latest_endpoint_scan(endpoint, scan_type):
    return (
        EndpointGenericScan.objects.all()
        .filter(endpoint=endpoint, is_the_latest_scan=True, type=scan_type, comply_or_explain_is_explained=False)
        .first()
    )


def add_bot_explanation(scan: EndpointGenericScan, explanation: str, duration: timedelta):
    scan.comply_or_explain_is_explained = True
    scan.comply_or_explain_case_handled_by = "WebSecMap Explanation Bot"
    scan.comply_or_explain_explained_by = "Websecmap Explanation Bot"
    scan.comply_or_explain_explanation = explanation
    scan.comply_or_explain_explained_on = datetime.now(pytz.utc)
    scan.comply_or_explain_explanation_valid_until = datetime.now(pytz.utc) + duration
    scan.save()


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

    # check if the issuer matches
    # <Name(C=US,ST=Washington,L=Redmond,O=Microsoft Corporation,OU=Microsoft IT,CN=Microsoft IT TLS CA 5)>
    _names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    names = [name.value for name in _names]
    if names[0] not in applicable_subdomains[scan.endpoint.url.computed_subdomain]:
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


def autoexplain_pki_subdomain():
    """
    Subdomains: pki

    Deviation: no https endpoint is needed. If none is found, and a warning is issued, this will counteract the standard
    finding.

    :return:
    """

    # applicable_subdomains = 'pki'
    # scan_type = 'plain_https'
    raise NotImplementedError
