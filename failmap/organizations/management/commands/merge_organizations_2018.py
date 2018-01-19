import logging
from copy import deepcopy
from datetime import datetime
from typing import List

import pytz
from django.core.management.commands.dumpdata import Command as DumpDataCommand
from django.db import transaction

from failmap.organizations.models import Coordinate, Organization, Promise, Url

log = logging.getLogger(__package__)

# geography update needs to have a OSM connection, otherwise it takes too long to process all new coordinates.
# woot.


@transaction.atomic
class Command(DumpDataCommand):
    help = "Starting point for merging organizations"

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        merge_date = datetime(year=2018, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        """
        De gemeenten Menaldumadeel, Franekeradeel en Het Bildt zullen opgaan in een nieuwe gemeente Waadhoeke.
        """
        merge(["Menaldumadeel", "Franekeradeel", "Het Bildt"], "Waadhoeke", merge_date)

        """
        Ook de dorpen Welsrijp, Winsum, Baijum en Spannum van gemeente Littenseradiel,
        sluiten zich bij deze nieuwe gemeente aan.
        """
        # todo: do a geographic move. We might do that with the django extensions, or import new data from openstreetmap
        # if you load new data from OSM, it should have all correct locations and regions. It would be better to
        # automate this away, instead of doing any manual guesses and such. This might be a tough job.

        """
        De gemeenteraad van Leeuwarderadeel heeft na een referendum in maart 2013 besloten dat de gemeente zal
        opgaan in de gemeente Leeuwarden.
        """
        merge(["Leeuwarderadeel"], "Leeuwarden", merge_date)

        """
        Ook zullen tien dorpen van Littenseradiel aan de nieuwe fusiegemeente toegevoegd worden.
        """
        # todo: another geographic move

        """
        De overige vijftien dorpen van Littenseradiel zullen bij de gemeente Súdwest-Fryslân worden gevoegd.
        """
        # todo: another geographic move

        """
        De gemeenten Rijnwaarden en Zevenaar hebben in mei 2016 besloten om te fuseren tot de nieuwe gemeente Zevenaar.
        """
        # straightforward geographic move
        merge(["Rijnwaarden"], "Zevenaar", merge_date)

        """
        De gemeenten Vlagtwedde en Bellingwedde hebben in oktober 2015 besloten om te fuseren tot de
        nieuwe gemeente Westerwolde.
        """
        # straightforward geographic move
        merge(["Vlagtwedde", "Bellingwedde"], "Westerwolde", merge_date)

        """
        De gemeenten Hoogezand-Sappemeer, Menterwolde en Slochteren hebben in november 2015 besloten om te fuseren
        tot de nieuwe gemeente Midden-Groningen.
        """

        # straightforward geographic move
        merge(["Hoogezand-Sappemeer", "Menterwolde", "Slochteren"], "Midden-Groningen", merge_date)


# implies that name + country + organization_type is unique.
@transaction.atomic
def merge(source_organizations_names: List[str], target_organization_name: str, when: datetime,
          organization_type: str="Municipality", country: str="NL"):
    """
    Keeping historical data correct is important.
    - The old organization should be visible, exactly as it was at that moment (geography), with the same ratings and
    urls. No new URLS should be added and the old (gone). We will not write code to enforce any of this, as we're all
    adults here.

    Situation 1: a new organization is created from older ones. This is recognizable due to a new name.
    - It copies all related data to itself. The history is needed to get a starting point / current rating.
    - A "created_on" is needed, so the new organization is not displayed in the past.
    - A "deleted_on" is needed on the previous organizations (with date + reason) so they are not shown in the future.

    Situation 2: an existing organization gets all the goodies:
    Solution 1: use the existing organization record:
    You cannot copy the history of the urls, as that changes the existing organization. It Can have the urls but they
    need to be re-scanned. This sounds like an aweful approach that mixes data. You might copy the last scans on the
    urls to get a starting point. But still: what is the advantage of mixing organizations like this? What if you want
    to undo this, then it's not clear what has been merged when. Just to save "one record" it adds a lot of complexity
    and opens the door to mistakes. We have to make solution 2 anyway, which is much clearer.

    Solution 2:
    The best way is to make a new organization and do the same as in situation 1.

    Optimizations:
    We have to take into account when rating an organization that it might be dead at some point. Also scans don't need
    to be performed after an organization is dead.

    In both scenario 1 and 2, a simple coordinate-copy is performed. This will employ the same pattern as other delete
    days: a created_on, a deleted_on (+date and reason). This way any coordinate layout can be valid for any
    organization.

    We can decide to only copy the last scan for each url, to get a starting history (we don't need anything before the
    merge, as that is already in other organizations). This way the organization starts out with the exact same data
    as the previous ones left off, without the (long) history.


    - Just alter the coordinates (and merge the old coordinates into one in this method, whereby you can import new
    coordinates from OSM, together with a date from when they are valid).

    Situation 3: special cases:
    Some villages are moved to another municipality. This means the urls have to be moved. This is currently not
    supported automatically and can be done by hand. It might be needed to make it easier to "transfer" an url
    to another organization "since" a certain date (effectively making also a copy, so the history of this URL stays
    in tact in the original old organization).


    Decisions:
    - Always make a new organization, weather it exists or not. (there are organizations with the same way, following
    the stacking pattern).
    - Make sure all coordinates from previous organization are assigned to the new one. They might be updated doing a
      coordinate import (some borders might move after at the final decision, even if it's miniscule).
    - Only copy the last scan information to the new organization ("depends on what the current date of running this is)


    :param organizations:
    :param target_organization:
    :param when:
    :return:
    """

    new_organization = Organization()
    new_organization.type = organization_type
    new_organization.country = country
    new_organization.name = target_organization_name
    new_organization.created_on = when
    new_organization.is_dead = False

    # todo: ? Store information that the organization stems from a previous organization.

    # Get the currently existing organization
    # implies that name + country + organization_type is unique.
    # Might result in an Organization.DoesNotExist, which means the transactions is rolled back.
    original_target = Organization.objects.get(
        name=target_organization_name, country=country, type=organization_type, is_dead=False)
    new_organization.twitter_handle = original_target.twitter_handle

    log.info("Creating a new %s, with information from the merged organization." % target_organization_name)
    original_target.is_dead = True
    original_target.is_dead_since = when
    original_target.is_dead_reason = "Merged with other organizations, using a similar name."
    original_target.save()

    # save the clone of the organization.
    new_organization.save()

    for source_organizations_name in source_organizations_names:
        with Organization.objects.get(
                name=source_organizations_name,
                country=country,
                type=organization_type, is_dead=False) as source_organization:

            # copy the coordinates from all to-be-merged organizations into the target
            for coordinate in Coordinate.objects.all().filter(organization=source_organization):
                cloned_coordinate = deepcopy(coordinate)
                cloned_coordinate.id = None
                cloned_coordinate.organization = new_organization
                cloned_coordinate.save()

            # still active promises
            for promise in Promise.objects.all().filter(
                    rganization=source_organization,
                    expires_on__gte=datetime.now(pytz.utc)):
                cloned_promise = deepcopy(promise)
                cloned_promise.id = None
                cloned_promise.organization = new_organization
                cloned_promise.save()

            # Should we make copies of all urls? And for what? Or should we state somewhere when an URL was owned
            # by an organization? Like n-n with extra information from when that is valid? That would result in
            # even more administration overhead?

            # No: this should not answer "since when did what organization gain what access to an url".
            # This question might arise in the future, but it has never been an issue.
            # It is more then enough to have a date from when a (new) organization started to exist. This implies
            # that from that moment the URLS for that organization where valid.
            # This approach might result in a bit of overhead for rebuilds, but hey: it's less complicated with
            # less administration.

            # In any case, there should not be a duplicate of the Url: it only exists once (or stacking).

            # add the target to all urls managed by the source_organization
            for url in Url.objects.all().filter(organization=source_organization):
                url.organization.add(new_organization)
                url.save()

    # todo:
    # Update the map viewers, to only show the existing organizations at that time.
    # Change the default rating algorithm to match the date in the organization and have a fallback.

    raise NotImplemented
