import logging
import socket
from base64 import b64decode, b64encode
from datetime import datetime
from typing import List

import OpenSSL
import pytz
from celery import Task, group
from django.utils import timezone
from OpenSSL import SSL
from OpenSSL.crypto import FILETYPE_PEM, dump_certificate, load_certificate
from OpenSSL.SSL import Error as SSLError
from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.autoexplain import add_bot_explanation
from websecmap.scanners.models import EndpointGenericScan
from websecmap.scanners.scanner import finish_those_that_wont_be_scanned, unique_and_random
from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES

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


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_scan():
    urls = [scan.endpoint.url for scan in query]
    plannedscan.request(activity="scan", scanner=SCANNER, urls=unique_and_random(urls))


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_scan_task(urls: List[Url]) -> Task:
    scans = list(set(query.filter(endpoint__url__in=urls)))
    finish_those_that_wont_be_scanned(SCANNER, scans, urls)

    tasks = [
        get_cert_chain.si(url=scan.endpoint.url.url, port=scan.endpoint.port, ip_version=scan.endpoint.ip_version).set(
            queue=CELERY_IP_VERSION_QUEUE_NAMES[scan.endpoint.ip_version]
        )
        | certificate_chain_ends_on_non_trusted_dutch_root_ca.s()
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
    # (SSL.SSLv3_METHOD, "SSL.SSLv3_METHOD"), not supported by openssl anymore
    # (SSL.SSLv2_METHOD, "SSL.SSLv2_METHOD"), not supported by openssl anymore
]


@app.task(expires=EXPIRES_IN_ONE_DAY)
def get_cert_chain(url, port, ip_version) -> List[OpenSSL.crypto.X509]:
    chain = []
    for method, method_name in methods:
        chain = get_cert_chain_call(url, port, ip_version, method, method_name)
        if chain:
            return chain
    return chain


# https://badssl.com/
def get_cert_chain_call(url, port, ip_version, method, method_name):
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
            conn.connect((url, port))
            conn.setblocking(1)
            conn.do_handshake()
            conn.set_tlsext_host_name(url.encode())

            # Deal with WantReadError errors, probably not needed with setblocking
            # attempts = 300
            # attempt = 0
            # while attempt <= attempts:
            #     try:
            #         attempt += 1
            #         conn.do_handshake()
            #     except SSL.WantReadError:
            #         sleep(0.01)
            #         conn.bio_read(4096)
            #     else:
            #         break

            chain = conn.get_peer_cert_chain()
            conn.close()
            return serialize_cert_chain(chain) if chain else []

    except ValueError:
        # SSLv2_METHOD and SSLv3_METHOD
        # ValueError("No such protocol")
        return []

    except SSLError:
        # OpenSSL.SSL.Error: [('SSL routines', 'ssl_choose_client_version', 'wrong ssl version')]
        return []

    except socket.gaierror:
        # socket.gaierror: [Errno 8] nodename nor servname provided, or not known
        # basically not resolving. Given this scanner will not kill off anything that doesnt resolve...
        return []

    except socket.error:
        # timeout reached probably
        return []

    # get address info error (DNS issues) can be retried a few times.
    except Exception as my_exception:  # noqa  # pylint: disable=broad-except
        # Log these exceptions to see what happens.
        log.exception(my_exception, extra={"hostname": url, "port": port, "ip": ip_version, "method": method_name})
        # Name does not resolve, wantread errors etc etc etc... there is no great code out there and can't make it
        return []


def serialize_cert_chain(certificates: List[OpenSSL.crypto.X509]) -> List[str]:
    # kombu.exceptions.EncodeError: cannot pickle '_cffi_backend.__CDataGCP' object
    return [b64encode(dump_certificate(FILETYPE_PEM, certificate)).decode("UTF-8") for certificate in certificates]


def deserialize_cert_chain(certificates: List[str]) -> List[OpenSSL.crypto.X509]:
    return [load_certificate(FILETYPE_PEM, b64decode(certificate)) for certificate in certificates]


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def certificate_chain_ends_on_non_trusted_dutch_root_ca(serialized_certificates: List[str]) -> bool:
    # todo: there are more untrusted certificates from the dutch state.
    # Example: https://secure-t.sittard-geleen.nl
    # https://www.pyopenssl.org/en/stable/api/crypto.html
    if not serialized_certificates:
        log.debug("No certificates received.")
        return False

    if not isinstance(serialized_certificates, List):
        log.debug("No certificates received (not even a list of items).")
        return False

    certificates = deserialize_cert_chain(serialized_certificates)

    last_cert: OpenSSL.crypto.X509 = certificates[-1]

    if not isinstance(last_cert, OpenSSL.crypto.X509):
        log.debug("Not an x509 instance but a %s.", type(last_cert))
        return False

    expected_digest = b"C6:C1:BB:C7:1D:4F:30:C7:6D:4D:B3:AF:B5:D0:66:DE:49:9E:9A:2D"
    expected_serial = 10004001
    expected_issuer = "/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Root CA - G1"
    expected_subject = "/C=NL/O=Staat der Nederlanden/CN=Staat der Nederlanden Private Root CA - G1"
    expected_notafter = b"20281113230000Z"  # Date in UTC, not in dutch time :)

    if last_cert.get_notAfter() != expected_notafter:
        log.debug("No cert match on expected expiration date.")
        return False

    if last_cert.digest("sha1") != expected_digest:
        log.debug("No cert match on digest.")
        return False

    if last_cert.get_serial_number() != expected_serial:
        log.debug("No cert match on serial.")
        return False

    issuer = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in last_cert.get_issuer().get_components()
    )
    if issuer != expected_issuer:
        log.debug("No cert match on issuer.")
        return False

    subject = "".join(
        f"/{name.decode():s}={value.decode():s}" for name, value in last_cert.get_subject().get_components()
    )
    if subject != expected_subject:
        log.debug("No cert match on subject.")
        return False

    log.debug("Certificate match!")
    return True


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def store_bot_explaination_if_needed(needed: bool, scan_id: int):
    scan = EndpointGenericScan.objects.all().filter(pk=scan_id).first()
    if not scan:
        return

    if needed:
        add_bot_explanation(scan, EXPLANATION, datetime(2028, 11, 14, tzinfo=pytz.utc) - timezone.now())
