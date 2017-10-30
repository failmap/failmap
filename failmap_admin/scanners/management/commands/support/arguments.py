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


def valid_organization(name):
    if "_ALL_" in name:
        return "_ALL_"
    try:
        o = Organization.objects.get(name=name)
        return o.name
    except ObjectDoesNotExist:
        msg = "%s is not a valid organization or _ALL_" % name
        raise argparse.ArgumentTypeError(msg)
