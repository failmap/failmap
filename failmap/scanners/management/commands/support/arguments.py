import argparse

from django.core.exceptions import ObjectDoesNotExist

from failmap.organizations.models import Organization


def add_organization_argument(parser):
    return parser.add_argument(
        '--organization', '-o',
        help="Name of an organization, for example Arnhem. Prefix spaces with a backslash (\\)",
        nargs=1,
        required=False,
        type=valid_organization
    )


def valid_organization(name):
    if name in ["_ALL_", "*"]:
        return "*"
    try:
        o = Organization.objects.get(name=name)
        return o.name
    except ObjectDoesNotExist:
        raise argparse.ArgumentTypeError("%s is not a valid organization or _ALL_" % name)
