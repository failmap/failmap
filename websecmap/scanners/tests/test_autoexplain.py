import datetime
import json
import logging

import pytz
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import websecmap
from websecmap.organizations.models import Url
from websecmap.scanners.autoexplain import (
    autoexplain_trust_microsoft,
    certificate_matches_microsoft_exception_policy,
    autoexplain_no_https_microsoft,
    certificate_chain_ends_on_non_trusted_dutch_root_ca,
    explain_headers_for_explained_microsoft_trusted_tls_certificates,
)
from websecmap.scanners.models import Endpoint, EndpointGenericScan

log = logging.getLogger("websecmap")


def test_certificate_chain_ends_on_non_trusted_dutch_root_ca(current_path):
    """
    To create a test chain:
    certificates = get_cert_chain('secure-t.sittard-geleen.nl', 443)
    dump = [b64encode(dump_certificate(FILETYPE_PEM, certificate)).decode('UTF-8') for certificate in certificates]
    """

    # Validate a complete chain that ends in the desired root certificate
    with open(f"{current_path}/websecmap/scanners/tests/autoexplain/valid_chain.json") as f:
        certificate_data = json.load(f)
    assert certificate_chain_ends_on_non_trusted_dutch_root_ca(certificate_data) is True

    # Fail to validate something that does not end in the root certificate
    with open(f"{current_path}/websecmap/scanners/tests/autoexplain/missing_root.json") as f:
        certificate_data = json.load(f)
    assert certificate_chain_ends_on_non_trusted_dutch_root_ca(certificate_data) is False

    # Supplying garbage causes no problems / crashes:
    assert certificate_chain_ends_on_non_trusted_dutch_root_ca([]) is False
    assert certificate_chain_ends_on_non_trusted_dutch_root_ca("asdasd") is False


def test_autoexplain_no_https_microsoft(db, mocker):
    url, created = Url.objects.all().get_or_create(url="autodiscover.arnhem.nl")
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol="http", port=80, ip_version=4)
    endpointscan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating="25",
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=True,
        type="plain_https",
    )

    class Answer:
        # <DNS name autodiscover.westerkwartier.nl.>
        # str(a.name)
        # Out[18]: 'autodiscover.westerkwartier.nl.'
        name: str = ""

        def __init__(self, name):
            self.name = name

        def __str__(self):
            return self.name

    # The answer is sort of a list... here we sort of emulate that.
    # '<dns.resolver.Answer object at 0x1136d1d60>'
    # for z in a:
    #   print(z)

    # mock dns.resolver.query(scan.endpoint.url.url, 'CNAME') in several ways:
    log.debug("mydomain.com is not a valid cname record in this case.")
    mocker.patch("dns.resolver.query", return_value=[Answer("mydomain.com")])
    autoexplain_no_https_microsoft()
    my_epgs = EndpointGenericScan.objects.all().first()
    assert my_epgs.comply_or_explain_is_explained is False

    log.debug("The cname must match exactly to the desired cname.")
    mocker.patch("dns.resolver.query", return_value=[Answer("autodiscover.outlook.com.mydomain.com")])
    autoexplain_no_https_microsoft()
    my_epgs = EndpointGenericScan.objects.all().first()
    assert my_epgs.comply_or_explain_is_explained is False

    log.debug("It should be an exact match to this value.")
    mocker.patch("dns.resolver.query", return_value=[Answer("autodiscover.outlook.com.")])
    autoexplain_no_https_microsoft()
    my_epgs = EndpointGenericScan.objects.all().first()
    assert my_epgs.comply_or_explain_is_explained is True


def test_autoexplain_certificate(db):
    url, created = Url.objects.all().get_or_create(url="autodiscover.arnhem.nl")
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol="https", port="443", ip_version=4)
    endpointscan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating="not trusted",
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=True,
        type="tls_qualys_certificate_trusted",
    )

    applicable_subdomains = {
        "autodiscover": ["accepted.test.example"],
    }
    trusted_organization = "Nonsense Corporation"

    # wrong subject
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate("subject"), endpointscan, applicable_subdomains, trusted_organization
    )

    # wrong issuer
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate("issuer"), endpointscan, applicable_subdomains, trusted_organization
    )

    # valid in the future
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate("future"), endpointscan, applicable_subdomains, trusted_organization
    )

    # expired
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate("expired"), endpointscan, applicable_subdomains, trusted_organization
    )

    assert True is certificate_matches_microsoft_exception_policy(
        generate_certificate(), endpointscan, applicable_subdomains, trusted_organization
    )


def generate_certificate(failure_mode: str = ""):
    # Code taken from https://cryptography.io/en/latest/x509/reference/

    one_day = datetime.timedelta(1, 0, 0)
    # weak key size, to make test faster
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=512, backend=default_backend())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()

    if failure_mode == "subject":
        builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "some.other.subdomain")]))
    else:
        builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "accepted.test.example")]))

    if failure_mode == "issuer":
        builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Failure Corporation")]))
    else:
        builder = builder.issuer_name(
            x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Nonsense Corporation")])
        )

    if failure_mode == "future":
        builder = builder.not_valid_before(datetime.datetime.today() + one_day)
        builder = builder.not_valid_after(datetime.datetime.today() + (one_day * 30))
    elif failure_mode == "expired":
        builder = builder.not_valid_before(datetime.datetime.today() - (one_day * 30))
        builder = builder.not_valid_after(datetime.datetime.today() - one_day)

    else:
        builder = builder.not_valid_before(datetime.datetime.today() - one_day)
        builder = builder.not_valid_after(datetime.datetime.today() + (one_day * 30))

    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName("cryptography.io")]), critical=False)
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    certificate = builder.sign(private_key=private_key, algorithm=hashes.SHA256(), backend=default_backend())

    return certificate


def generate_specific_certificate(subject="", issuer=""):
    one_day = datetime.timedelta(1, 0, 0)
    # weak key size, to make test faster
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=512, backend=default_backend())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
    builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, issuer)]))
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + (one_day * 30))
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName("cryptography.io")]), critical=False)
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    certificate = builder.sign(private_key=private_key, algorithm=hashes.SHA256(), backend=default_backend())

    return certificate


# overwrite the retrieve_certificate method in autoexplain. Otherwise it tries to access the internet.
def fake_retrieve_certificate(*args, **kwargs):
    return generate_specific_certificate("*.online.lync.com", "Microsoft Corporation")


def test_autoexplain_including_headers(db, monkeypatch):
    url, created = Url.objects.all().get_or_create(url="lyncdiscover.arnhem.nl")
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol="https", port="443", ip_version=4)
    endpointscan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating="not trusted",
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=True,
        type="tls_qualys_certificate_trusted",
    )
    header_scan_new, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating="not trusted",
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=True,
        type="http_security_header_x_content_type_options",
    )
    header_scan_old, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating="not trusted",
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=False,
        type="http_security_header_x_content_type_options",
    )

    assert endpointscan.comply_or_explain_is_explained is False
    assert header_scan_new.comply_or_explain_is_explained is False
    assert header_scan_old.comply_or_explain_is_explained is False

    log.debug("explaining...")
    monkeypatch.setattr(websecmap.scanners.autoexplain, "retrieve_certificate", fake_retrieve_certificate)

    autoexplain_trust_microsoft()

    updated_endpoint = EndpointGenericScan.objects.get(id=endpointscan.id)
    assert updated_endpoint.comply_or_explain_is_explained is True
    updated_endpoint = EndpointGenericScan.objects.get(id=header_scan_new.id)
    assert updated_endpoint.comply_or_explain_is_explained is True
    updated_endpoint = EndpointGenericScan.objects.get(id=header_scan_old.id)
    assert updated_endpoint.comply_or_explain_is_explained is False

    # Verify that headers are explained even when the TLS certificate has been explained
    egs = EndpointGenericScan.objects.get(id=header_scan_new.id)
    egs.comply_or_explain_is_explained = False
    egs.save()

    explain_headers_for_explained_microsoft_trusted_tls_certificates()
    egs = EndpointGenericScan.objects.get(id=header_scan_new.id)
    egs.comply_or_explain_is_explained = True
