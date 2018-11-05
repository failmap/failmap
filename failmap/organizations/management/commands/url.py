import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand

from failmap.organizations.models import Organization, Url

log = logging.getLogger(__package__)


class Command(BaseCommand):
    """
    Allows you to check the existence of urls and allows you to add them to several organizations by name.

    Asks to add the urls to organizations.
    """

    def add_arguments(self, parser):
        """Add arguments."""
        parser.add_argument('-u', '--urls', type=str, nargs='+', help='space separated urls')
        super(Command, self).add_arguments(parser)

    def handle(self, *args, **options):

        non_existing = get_non_existing(options['urls'])

        if non_existing:
            log.info("Found new urls, to what organizations do you want to add these?")
            log.info("The new urls are: %s" % " ".join(non_existing))
            organizations = inquire_organization()

            for url in non_existing:

                new_url = Url()
                new_url.url = url
                new_url.created_on = datetime.now(pytz.utc)
                new_url.save()

                for organization in organizations:

                    new_url.organization.add(organization)
                    new_url.save()

                    log.info("Added %s to %s" % (url, organization))


def get_non_existing(urls):

    not_exists = []

    for url in urls:
        exists = Url.objects.all().filter(url=url).exists()
        if exists:
            log.debug("Exists: %s" % url)
        else:
            log.debug("Does NOT exist: %s" % url)
            not_exists.append(url)

    if not_exists:
        log.debug("These urls do not exist:")
        log.debug(" ".join(not_exists))

    return not_exists


def inquire_organization():
    """
    Get one or more organizations to add urls to.
    :return:
    """
    organizations = []

    while True:
        if organizations:
            log.info("Currently adding to: %s" % organizations)

        possible_organization = input("Type the name of an organization, type - to be done: ")

        if possible_organization in ["-", ""]:
            break

        # does not take into account country or organization type, so it's not perfect.
        real_organization = Organization.objects.all().filter(name__iexact=possible_organization, is_dead=False).first()

        # don't add None search result.
        if real_organization:
            organizations.append(real_organization)

    return organizations
