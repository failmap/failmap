import logging
import socket
from base64 import b64decode, b64encode
from datetime import datetime, timezone
from typing import List

import OpenSSL
from celery import Task, group
from OpenSSL import SSL
from OpenSSL.crypto import FILETYPE_PEM, dump_certificate, load_certificate
from OpenSSL.SSL import Error

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner import finish_those_that_wont_be_scanned, unique_and_random
from dataclasses import dataclass

log = logging.getLogger(__package__)

SCANNER = "autoexplain_dutch_untrusted_cert"
EXPLANATION = "state_trusted_root_ca"

query = EndpointGenericScan.objects.all().filter(
    # Dont include all dead endpoints and urls, as it slows things down and are not used in reports anyway:
    endpoint__is_dead=False,
    endpoint__url__not_resolvable=False,
    endpoint__url__is_dead=False,
    # Assuming this is for the dutch market only. Strictly speaking it could be anything, yet highly unusual.
    endpoint__url__computed_suffix="nl",
    type="tls_qualys_certificate_trusted",
    is_the_latest_scan=True,
    comply_or_explain_is_explained=False,
    endpoint__protocol="https",
    rating="not trusted",
)


@app.task(queue="kickoff", ignore_result=True)
def plan_scan():
    urls = [scan.endpoint.url for scan in query]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls: List[Url]) -> Task:
    scans = list(set(query.filter(endpoint__url__in=urls)))
    finish_those_that_wont_be_scanned(SCANNER, scans, urls)

    tasks = [
        get_cert_chain.si(url=scan.endpoint.url.url, port=scan.endpoint.port, ip_version=scan.endpoint.ip_version)
        | certificate_chain_contains_trusted_untrusted_certificate.s()
        | store_bot_explaination_if_needed.s(scan.pk)
        | plannedscan.finish.si("scan", SCANNER, scan.endpoint.url.pk)
        for scan in scans
    ]

    return group(tasks)


# https://www.pyopenssl.org/en/stable/api/ssl.html
# todo: upgrade pyopenssl and support TLS_METHOD for tls 1.3
# from new to obsolete...
methods = [
    (SSL.TLSv1_2_METHOD, "SSL.TLSv1_2_METHOD"),
    (SSL.TLSv1_1_METHOD, "SSL.TLSv1_1_METHOD"),
    (SSL.TLSv1_METHOD, "SSL.TLSv1_METHOD"),
    (SSL.SSLv23_METHOD, "SSL.SSLv23_METHOD"),
    # https://www.pyopenssl.org/en/stable/api/ssl.html
    # New code should only use TLS_METHOD, TLS_SERVER_METHOD, or TLS_CLIENT_METHOD.
    (SSL.TLS_METHOD, "SSL.TLS_METHOD"),
    # (SSL.SSLv3_METHOD, "SSL.SSLv3_METHOD"), not supported by openssl anymore
    # (SSL.SSLv2_METHOD, "SSL.SSLv2_METHOD"), not supported by openssl anymore
]


def command_line_cert_check(url: str, port: int = 443, ip_version: int = 4):
    # for debugging:
    # from websecmap.scanners.scanner.autoexplain_dutch_untrusted_cert import *
    # log.setLevel(logging.DEBUG)
    chain = get_cert_chain(url=url, port=port, ip_version=ip_version)
    return certificate_chain_contains_trusted_untrusted_certificate(chain)


# placed on the prefork worker because gevent messes with the ssl library and causes want/read errors.
# prefork workers run the original tls code which works as intended and supports this edge case measurement
@app.task(queue="prefork")
def get_cert_chain(url: str, port, ip_version) -> List[str]:
    port = int(port)
    chain = []
    log.debug("Attempting to retrieve SSL chert via %s different methods.", len(methods))
    for method, method_name in methods:
        log.debug("Attempting to retrieve SSL chert via SSL method %s.", method_name)
        chain = get_cert_chain_call(url, port, ip_version, method, method_name)
        if chain:
            log.debug("Returning cert chain.")
            return chain
    log.debug("Could not retrieve cert chain via all available methods, returning nothing.")
    return chain


# https://badssl.com/
def get_cert_chain_call(url: str, port, ip_version, method, method_name):
    # https://stackoverflow.com/questions/19145097/getting-certificate-chain-with-python-3-3-ssl-module
    # Relatively new Dutch governmental sites relying on anything less < TLS 1.2 is insane.
    log.debug("Retrieving certificate chain from %s:%s via ipv%s on tls method %s.", url, port, ip_version, method_name)
    try:
        # Todo: does still go to the ipv4 version if told to user AF-INET6. The workers should restrict it.
        # Decide which IP-version to use
        socket_ip_version = socket.AF_INET if ip_version == 4 else socket.AF_INET6
        # Use with statements so sockets/connections close automatically
        with socket.socket(socket_ip_version, socket.SOCK_STREAM) as sock:
            # future methods only need TLS_METHOD....
            sock.settimeout(10)
            conn = SSL.Connection(context=SSL.Context(method), socket=sock)
            # this sets the hostname so this works in SNI setups
            conn.set_tlsext_host_name(url.encode())
            conn.connect((url, port))
            conn.setblocking(1)
            conn.do_handshake()
            chain = conn.get_peer_cert_chain()
            conn.close()
            log.debug("Dutch Untrusted Cert: chain retrieved: %s, port, %s, ip_version, %s.", url, port, ip_version)
            return serialize_cert_chain(chain) if chain else []
    except ValueError as error:
        log.debug("Dutch Untrusted Cert:Value Error: on url %s, port, %s, ip_version, %s.", url, port, ip_version)
        log.debug(error)
        # SSLv2_METHOD and SSLv3_METHOD
        # ValueError("No such protocol")
        return []
    except Error as error:
        log.debug("Dutch Untrusted Cert: sslerror on url %s, port, %s, ip_version, %s.", url, port, ip_version)
        log.debug(error)
        # OpenSSL.SSL.Error: [('SSL routines', 'ssl_choose_client_version', 'wrong ssl version')]
        return []
    except socket.gaierror as error:
        log.debug("Dutch Untrusted Cert: socket.gaierror: on url %s, port, %s, ip_version, %s.", url, port, ip_version)
        log.debug(error)
        # socket.gaierror: [Errno 8] nodename nor servname provided, or not known
        # basically not resolving. Given this scanner will not kill off anything that doesnt resolve...
        return []
    except socket.error as error:
        log.debug("Dutch Untrusted Cert: socket.error: on url %s, port, %s, ip_version, %s.", url, port, ip_version)
        log.debug(error)
        # timeout reached probably
        return []
    # get address info error (DNS issues) can be retried a few times.
    except Exception as my_exception:  # noqa  # pylint: disable=broad-except
        log.debug("Dutch Untrusted Cert: Generic Exception: url %s, port, %s, ip_version, %s.", url, port, ip_version)
        # Log these exceptions to see what happens.
        log.exception(my_exception, extra={"hostname": url, "port": port, "ip": ip_version, "method": method_name})
        # Name does not resolve, wantread errors etc etc etc... there is no great code out there and can't make it
        return []


def serialize_cert_chain(certificates: List[OpenSSL.crypto.X509]) -> List[str]:
    # kombu.exceptions.EncodeError: cannot pickle '_cffi_backend.__CDataGCP' object
    return [b64encode(dump_certificate(FILETYPE_PEM, certificate)).decode("UTF-8") for certificate in certificates]


def deserialize_cert_chain(certificates: List[str]) -> List[OpenSSL.crypto.X509]:
    return [load_certificate(FILETYPE_PEM, b64decode(certificate)) for certificate in certificates]


@app.task(queue="database")
def certificate_chain_contains_trusted_untrusted_certificate(serialized_certificates: List[str]) -> bool:
    # todo: there are more untrusted certificates from the dutch state.
    # Example: https://secure-t.sittard-geleen.nl
    # https://www.pyopenssl.org/en/stable/api/crypto.html
    if not serialized_certificates:
        log.debug("Dutch Untrusted Cert: No certificates received.")
        return False
    if not isinstance(serialized_certificates, List):
        log.debug("Dutch Untrusted Cert: No certificates received (not even a list of items).")
        return False
    certificates = deserialize_cert_chain(serialized_certificates)
    # # perhaps check on the common name of the first cert...
    if len(certificates) == 1:
        log.debug("Dutch Untrusted Cert: Only one certificate received, this cannot be a trusted cert.")
        return False
    # how do we know this cert is the right cert exactly and not something that has been yolo-added to the chain?
    return any(is_acceptable_certificate(cert) for cert in certificates)


@dataclass
class AcceptableCertificate:
    digest: bytes
    serial: int
    issuer: str
    subject: str
    notafter: bytes


ACCEPTABLE_CERTIFICATES = [
    AcceptableCertificate(
        digest=b"C6:C1:BB:C7:1D:4F:30:C7:6D:4D:B3:AF:B5:D0:66:DE:49:9E:9A:2D",
        serial=10004001,
        issuer="/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Root CA - G1",
        subject="/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Root CA - G1",
        notafter=b"20281113230000Z",
    ),
    AcceptableCertificate(
        digest=b"03:67:7B:4E:C0:FF:CA:9D:3C:AD:6C:04:4A:73:3B:3E:7A:75:D1:FD",
        serial=10004104,
        issuer="/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Root CA - G1",
        subject="/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Services CA - G1",
        notafter=b"20281112230000Z",
    ),
    # this one was also on the site..., not yet requested. Time might be off.
    # AcceptableCertificate(
    #     digest=b"87:0C:A5:9F:98:4D:CD:F0:EB:C1:43:B7:3F:7C:88:9A:AD:4A:0F:B5",
    #     serial=5613314895991348523,
    #     issuer="/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Services CA - G1",
    #     subject="/C=NL/O=CIBG/CN=UZI-register Private Server CA G1",
    #     notafter=b"20281112000000Z",
    # ),
]


def inspect_certificate(certificate: OpenSSL.crypto.X509) -> None:
    issuer = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in certificate.get_issuer().get_components()
    )
    subject = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in certificate.get_subject().get_components()
    )
    print(f'digest={certificate.digest("sha1")},')
    print(f"serial={certificate.get_serial_number()},")
    print(f'issuer="{issuer}",')
    print(f'subject="{subject}",')
    print(f"notafter={certificate.get_notAfter()}")


def is_acceptable_certificate(certificate: OpenSSL.crypto.X509):
    # we've seen the g1 cert after a kpn root cert... so this g1 thing can be anywhere in the chain.
    # see: test-digikoppeling.eindhoven.nl
    if not isinstance(certificate, OpenSSL.crypto.X509):
        log.debug("Dutch Untrusted Cert: Not an x509 instance but a %s.", type(certificate))
        return False

    return any(cert_matches(certificate, acceptable_certificate) for acceptable_certificate in ACCEPTABLE_CERTIFICATES)


def cert_matches(certificate1: OpenSSL.crypto.X509, certificate2: AcceptableCertificate):
    if not all(
        [
            cert_digest_match(certificate1, certificate2.digest),
            cert_serial_match(certificate1, certificate2.serial),
            cert_issuer_match(certificate1, certificate2.issuer),
            cert_subject_match(certificate1, certificate2.subject),
            cert_notafter_match(certificate1, certificate2.notafter),
        ]
    ):
        log.debug("Dutch Untrusted Cert: Certificate does not match!")
        return False
    log.debug("Dutch Untrusted Cert: Certificate match!")
    return True


def cert_notafter_match(certificate: OpenSSL.crypto.X509, expected_notafter: bytes) -> bool:
    # Date in UTC, not in dutch time :)
    if certificate.get_notAfter() == expected_notafter:
        log.debug("Dutch Untrusted Cert: match on expected_notafter: %s.", expected_notafter)
        return True
    log.debug("Dutch Untrusted Cert: No cert match on expected expiration date.")
    return False


def cert_digest_match(certificate: OpenSSL.crypto.X509, expected_digest: bytes) -> bool:
    if certificate.digest("sha1") == expected_digest:
        log.debug("Dutch Untrusted Cert: match on expected digest: %s.", expected_digest)
        return True
    log.debug("Dutch Untrusted Cert: No cert match on digest.")
    return False


def cert_serial_match(certificate: OpenSSL.crypto.X509, expected_serial: int) -> bool:
    if certificate.get_serial_number() == expected_serial:
        log.debug("Dutch Untrusted Cert: match on expected serial: %s.", expected_serial)
        return True
    log.debug("Dutch Untrusted Cert: No cert match on serial.")
    return False


def cert_issuer_match(certificate: OpenSSL.crypto.X509, expected_issuer: str) -> bool:
    issuer = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in certificate.get_issuer().get_components()
    )
    if issuer == expected_issuer:
        log.debug("Dutch Untrusted Cert: match on expected serial: %s.", expected_issuer)
        return True
    log.debug("Dutch Untrusted Cert: No cert match on issuer.")
    return False


def cert_subject_match(certificate: OpenSSL.crypto.X509, expected_subject: str) -> bool:
    subject = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in certificate.get_subject().get_components()
    )
    if subject == expected_subject:
        log.debug("Dutch Untrusted Cert: match on expected serial: %s.", expected_subject)
        return True
    log.debug("Dutch Untrusted Cert: No cert match on subject.")
    return False


@app.task(queue="storage", ignore_result=True)
def store_bot_explaination_if_needed(needed: bool, scan_id: int):
    scan = EndpointGenericScan.objects.all().filter(pk=scan_id).first()
    if not scan:
        return

    if not needed:
        log.debug("Dutch Untrusted Cert: Certificate on scan_id is NOT a dutch state trusted cert: %s.", scan_id)
        return

    log.debug("Dutch Untrusted Cert: Certificate on scan_id is a dutch state trusted cert: %s.", scan_id)
    add_bot_explanation(scan, EXPLANATION, datetime(2028, 11, 14, tzinfo=timezone.utc) - datetime.now(timezone.utc))
