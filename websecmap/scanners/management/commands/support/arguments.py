import argparse

from django.core.exceptions import ObjectDoesNotExist

from websecmap.organizations.models import Organization


def add_organization_argument(parser):
    return parser.add_argument(
        "--organization",
        "-o",
        help="Name of an organization, for example Arnhem. Prefix spaces with a backslash (\\)",
        nargs=1,
        required=False,
        type=valid_organization,
    )


def valid_organization(name):
    if name in ["_ALL_", "*"]:
        return "*"
    try:
        org = Organization.objects.get(name__iexact=name)
        return org.name
    except ObjectDoesNotExist as exc:
        raise argparse.ArgumentTypeError(f"{name} is not a valid organization or _ALL_") from exc
