import logging
from datetime import datetime
from typing import List

import pytz
from django.core.management.base import BaseCommand

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.scanner.dns import discover_wildcard
from websecmap.scanners.scanner.http import resolves

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

        new_urls = get_new_urls(options['urls'])

        if not new_urls:
            return

        log.info("Found new urls, to what organizations do you want to add these?")
        log.info("The new urls are: %s" % " ".join(new_urls))
        organizations = inquire_organization()

        for url in new_urls:

            new_url = Url()
            new_url.url = url
            new_url.created_on = datetime.now(pytz.utc)
            new_url.save()

            for organization in organizations:

                new_url.organization.add(organization)
                new_url.save()

                log.info("Added %s to %s" % (url, organization))


def get_new_urls(urls: List[str]):

    new_urls = []

    for url in urls:
        # make sure urls are always lowercase.
        url = url.lower()
        exists = Url.objects.all().filter(url=url).exists()
        if exists:
            log.debug("Exists: %s" % url)
        else:
            # check for wildcard dns...
            if discover_wildcard(url):
                log.info("Cannot add %s because it's DNS has wildcards enabled. This means everything resolves. "
                         "Use -F to override this check and still add the url. (todo: support -f) :) lolopensource")
            else:
                if resolves(url):
                    log.debug("Does not exist in the database, it resolved: %s" % url)
                    new_urls.append(url)
                else:
                    log.debug("Does not exist in the database, but didn't resolve, so can't be added: %s" % url)
    if new_urls:
        log.debug("These urls do not exist:")
        log.debug(" ".join(new_urls))

    return new_urls


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
