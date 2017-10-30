import argparse

from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization


def add_organization_argument(parser):
    return parser.add_argument(
        '--organization', '-o',
        help="Name of an organization, for example Arnhem. Prefix spaces with a backslash (\\)",
        nargs=1,
        required=False,
        type=valid_organization
    )


def add_discover_verify(parser):
    return parser.add_argument(
        '--method', '-m',
        help="verify|discover. Verify checks all existing ones, discover tries to find new ones.",
        nargs='?',
        required=False,
        type=valid_discover_verify,
        default="verify"
    )


def valid_organization(name):
    if "_ALL_" in name:
        return "_ALL_"
    try:
        o = Organization.objects.get(name=name)
        return o.name
    except ObjectDoesNotExist:
        raise argparse.ArgumentTypeError("%s is not a valid organization or _ALL_" % name)


def valid_discover_verify(option):
    if option == "verify" or option == "discover":
        return option
    raise argparse.ArgumentTypeError("Method can be either 'discover' or 'verify'. Given: " % option)
