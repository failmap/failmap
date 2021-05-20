import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization, Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Copies urls from one organization to another. Will ask for confirmation before copying.
    """

    def add_arguments(self, parser):
        """Add arguments."""
        parser.add_argument("-s", "--source", type=str, help="Organization ID")
        parser.add_argument("-t", "--target", type=str, help="Organization ID")
        super(Command, self).add_arguments(parser)

    def handle(self, *args, **options):

        source = options.get("source", None)
        target = options.get("target", None)

        if not all([source, target]):
            raise ValueError("Both source and target are required.")

        source_organization = Organization.objects.all().filter(id=source).first()
        target_organization = Organization.objects.all().filter(id=target).first()

        if not all([source_organization, target_organization]):
            raise ValueError(
                f"Either source or target does not exist in the database. "
                f"Source: {source_organization}, target: {target_organization}"
            )

        print()
        print("Do you wish to copy the following urls from source to target?")
        print(f"Source urls from {source_organization}")
        source_urls = Url.objects.all().filter(organization=source_organization).values_list("url", flat=True)
        print(f"{len(source_urls)} urls in {source_organization}")
        print(", ".join(source_urls))
        print()
        print(f"Target to {target_organization}")
        target_urls = Url.objects.all().filter(organization=target_organization).values_list("url", flat=True)
        print(f"{len(target_urls)} urls in {target_organization}")
        print(", ".join(target_urls))

        print()
        print(
            f"Do you wish to copy the following urls from "
            f"'{source_organization.name}' to '{target_organization.name}'? This cannot be undone."
        )
        answer = input("y/N: ")

        if answer.lower() not in ["y", "yes", "yaas"]:
            print("Copy cancelled. Better luck next time.")

        source_urls = Url.objects.all().filter(organization=source_organization)
        for url in source_urls:
            print(f"Copying {url} to {target_organization}")
            url.organization.add(target_organization)

        print(f"Done, copied {len(source_urls)} urls.")
