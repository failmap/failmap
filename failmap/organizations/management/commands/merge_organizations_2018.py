import logging
from copy import deepcopy
from datetime import datetime
from typing import List

from django.core.management.commands.dumpdata import Command as DumpDataCommand

from failmap.organizations.models import Coordinate, Organization, Url

log = logging.getLogger(__package__)


class Command(DumpDataCommand):
    help = "Starting point for merging organizations"

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        # making sure this is not run in production yet.
        raise NotImplemented

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


def merge(organization_names: List[str], target_organization_name: str, when: datetime,
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

    target = Organization()
    target.type = organization_type
    target.country = country
    target.name = target_organization_name
    target.created_on = when

    try:
        source_target = Organization.objects.all().filter(
            name=target_organization_name, country=country, type=organization_type, is_dead=False)
        target.twitter_handle = source_target.twitter_handle

        log.info("Creating a new %s, with information from the merged organization." % target_organization_name)
        source_target.is_dead = True
        source_target.is_dead_since = when
        source_target.is_dead_reason = "Merged with other organizations, using a similar name."
        source_target.save()
    except Organization.DoesNotExist:
        pass

    target.save()

    for organization_name in organization_names:
        with Organization.objects.all().filter(
                name=organization_name, country=country, type=organization_type, is_dead=False) as source_organization:

            # copy the coordinates from all to-be-merged organizations into the target
            for coordinate in Coordinate.objects.all().filter(organization=source_organization):
                new_coordinate = deepcopy(coordinate)
                new_coordinate.id = None
                new_coordinate.organization = target
                new_coordinate.save()

            # still active promises

            # all living urls (including everything below it, otherwise you might alter data from the other org and you
            # will have a lot of "old stuff" to carry along with you.) Also will have more problems with urls
            # that are shared amongst organizations. It's better to manage that on a copy than to alter the original.
            for url in Url.objects.all().filter(organization=source_organization):
                raise NotImplemented
                # copy endpoints
                # copy urlips

                # copy last endpointgenericscan for each generic scan type
                # copy last tlsqualysscan
                # copy last screenshot

    # todo afterwards:
    # Update the map info, to only show the currently existing organizations.
    # The default creation date stays as it is. This will change the default rating algorithm.
    # add a default date to created_on for default ratings.

    raise NotImplemented
