import datetime
import logging

import pytz
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from websecmap.organizations.models import Url
from websecmap.scanners.autoexplain import certificate_matches_microsoft_exception_policy
from websecmap.scanners.models import Endpoint, EndpointGenericScan

log = logging.getLogger('websecmap')


def test_autoexplain(db):
    url, created = Url.objects.all().get_or_create(url='autodiscover.arnhem.nl')
    endpoint, created = Endpoint.objects.all().get_or_create(url=url, protocol='https', port='443', ip_version=4)
    endpointscan, created = EndpointGenericScan.objects.all().get_or_create(
        endpoint=endpoint,
        rating='not trusted',
        rating_determined_on=datetime.datetime.now(pytz.utc),
        is_the_latest_scan=True,
        type='tls_qualys_certificate_trusted')

    applicable_subdomains = {
        'autodiscover': ['accepted.test.example'],
    }
    trusted_organization = "Nonsense Corporation"

    # wrong subject
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate('subject'), endpointscan, applicable_subdomains, trusted_organization)

    # wrong issuer
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate('issuer'), endpointscan, applicable_subdomains, trusted_organization)

    # valid in the future
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate('future'), endpointscan, applicable_subdomains, trusted_organization)

    # expired
    assert False is certificate_matches_microsoft_exception_policy(
        generate_certificate('expired'), endpointscan, applicable_subdomains, trusted_organization)

    assert True is certificate_matches_microsoft_exception_policy(
        generate_certificate(), endpointscan, applicable_subdomains, trusted_organization)


def generate_certificate(failure_mode: str = ""):
    # Code taken from https://cryptography.io/en/latest/x509/reference/

    one_day = datetime.timedelta(1, 0, 0)
    # weak key size, to make test faster
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=512, backend=default_backend())
    public_key = private_key.public_key()
    builder = x509.CertificateBuilder()

    if failure_mode == "subject":
        builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'some.other.subdomain')]))
    else:
        builder = builder.subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u'accepted.test.example')]))

    if failure_mode == "issuer":
        builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                                                                    u'Failure Corporation')]))
    else:
        builder = builder.issuer_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME,
                                                                    u'Nonsense Corporation')]))

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
    builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(u'cryptography.io')]), critical=False)
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    certificate = builder.sign(private_key=private_key, algorithm=hashes.SHA256(), backend=default_backend())

    return certificate