from copy import deepcopy
from datetime import datetime
from typing import List

import pytz
from celery import group
from deepdiff import DeepDiff

from websecmap.celery import app
from websecmap.organizations.models import Organization, Url
from websecmap.reporting.models import OrganizationReport
from websecmap.reporting.report import log, get_latest_urlratings_fast, \
    aggegrate_url_rating_scores, relevant_urls_at_timepoint, START_DATE, significant_moments, get_allowed_to_report, \
    recreate_url_reports


def create_organization_report_on_moment(organization: Organization, when: datetime = None):
    """
    # also callable as admin action
    # this is 100% based on url ratings, just an aggregate of the last status.
    # make sure the URL ratings are up to date, they will check endpoints and such.

    :param organization:
    :param when:
    :return:
    """
    # If there is no time slicing, then it's today.
    if not when:
        when = datetime.now(pytz.utc)

    log.info("Creating report for %s on %s" % (organization, when, ))

    # if there already is an organization rating on this moment, skip it. You should have deleted it first.
    # this is probably a lot quicker than calculating the score and then deepdiffing it.
    # using this check we can also ditch deepdiff, because ratings on the same day are always the same.
    # todo: we should be able to continue on a certain day.
    if OrganizationReport.objects.all().filter(organization=organization, when=when).exists():
        log.info("Rating already exists for %s on %s. Not overwriting." % (organization, when))

    # Done: closing off urls, after no relevant endpoints, but still resolvable. Done.
    # if so, we don't need to check for existing endpoints anymore at a certain time...
    # It seems we don't need the url object, only a flat list of pk's for urlratigns.
    # urls = relevant_urls_at_timepoint(organizations=[organization], when=when)
    urls = relevant_urls_at_timepoint_organization(organization=organization, when=when)

    # Here used to be a lost of nested queries: getting the "last" one per url. This has been replaced with a
    # custom query that is many many times faster.
    all_url_ratings = get_latest_urlratings_fast(urls, when)
    scores = aggegrate_url_rating_scores(all_url_ratings)

    # Still do deepdiff to prevent double reports.
    try:
        last = OrganizationReport.objects.filter(
            organization=organization, when__lte=when).latest('when')
    except OrganizationReport.DoesNotExist:
        log.debug("Could not find the last organization rating, creating a dummy one.")
        last = OrganizationReport()  # create an empty one

    scores['name'] = organization.name
    calculation = {"organization": scores}

    # this is 10% faster without deepdiff, the major pain is elsewhere.
    if DeepDiff(last.calculation, calculation, ignore_order=True, report_repetition=True):
        log.info("The calculation for %s on %s has changed, so we're saving this rating." % (organization, when))

        # remove urls and name from scores object, so it can be used as initialization parameters (saves lines)
        # this is by reference, meaning that the calculation will be affected if we don't work on a clone.
        init_scores = deepcopy(scores)
        del(init_scores['name'])
        del(init_scores['urls'])

        organizationrating = OrganizationReport(**init_scores)
        organizationrating.organization = organization
        organizationrating.when = when
        organizationrating.calculation = calculation

        organizationrating.save()
        log.info("Saved report for %s on %s." % (organization, when))
    else:
        # This happens because some urls are dead etc: our filtering already removes this from the relevant information
        # at this point in time. But since it's still a significant moment, it will just show that nothing has changed.
        log.warning("The calculation for %s on %s is the same as the previous one. Not saving." % (organization, when))


def relevant_urls_at_timepoint_organization(organization: Organization, when: datetime):
    # doing this, without the flat list results in about 40% faster execution, most notabily on large organizations
    # if you want to see what's going on, see relevant_urls_at_timepoint
    # removed the IN query to gain some extra speed
    # returned a flat list of pk's, since we don't do anything else with these urls. It's not particulary faster.
    queryset = Url.objects.filter(organization=organization)
    return relevant_urls_at_timepoint(queryset, when)


@app.task(queue='storage')
def default_organization_rating(organizations: List[Organization]):
    """
    Generate default ratings so all organizations are on the map (as being grey). This prevents
    empty spots / holes.
    :return:
    """

    if not organizations:
        organizations = Organization.objects.all()

    for organization in organizations:
        log.info("Giving organization a default rating: %s" % organization)

        when = organization.created_on if organization.created_on else START_DATE

        r = OrganizationReport()
        r.when = when
        r.organization = organization
        r.calculation = {
            "organization": {
                "name": organization.name,
                "high": 0,
                "medium": 0,
                "low": 0,
                "ok": 0,
                "urls": []
            }
        }
        r.save()


@app.task(queue='storage')
def create_organization_reports_now(organizations: List[Organization]):

    for organization in organizations:
        now = datetime.now(pytz.utc)
        create_organization_report_on_moment(organization, now)


@app.task(queue='storage')
def recreate_organization_reports(organizations: List):
    """Remove organization rating and rebuild a new."""

    # todo: only for allowed organizations...

    for organization in organizations:
        log.info('Adding rating for organization %s', organization)

        # Given yuou're rebuilding, you have to delete all previous ratings:
        OrganizationReport.objects.all().filter(organization=organization).delete()

        # and then rebuild the ratings per moment. This is not really fast.
        # done: reduce the number of significants moments to be weekly in the past, which will safe a lot of time
        # not needed: the rebuild already takes a lot of time, so why bother with that extra hour or so.

        urls = Url.objects.filter(organization__in=organizations)
        moments, happenings = significant_moments(urls=urls, reported_scan_types=get_allowed_to_report())
        for moment in moments:
            create_organization_report_on_moment(organization, moment)

        # If there is nothing to show, use a fallback value to display "something" on the map.
        # We cannot add default ratings per organizations per-se, as they would intefear with the timeline.
        # for example: if an organization in 2018 is a merge of organizations in 2017, it will mean that on
        # january first 2018, there would be an empty and perfect rating. That would show up on the map as
        # empty which does not make sense. Therefore we only add a default rating if there is really nothing else.
        if not moments:
            # Make sure the organization has the default rating

            default_organization_rating(organizations=[organization])


@app.task(queue='storage')
def update_report_tasks(url_chunk: List[Url]):
    """
    A small update function that only rebuilds a single url and the organization report for a single day. Using this
    during onboarding, it's possible to show changes much faster than a complete rebuild.

    :param url_chunk: List of urls
    :return:
    """
    tasks = []

    for url in url_chunk:

        organizations = list(url.organization.all())

        # Note that you cannot determine the moment to be "now" as the urls have to be re-reated.
        # the moment to rerate organizations is when the url_ratings has finished.

        tasks.append(recreate_url_reports.si([url]) | create_organization_reports_now.si(organizations))

        # Calculating statistics is _extremely slow_ so we're not doing that in this method to keep the pace.
        # Otherwise you'd have a 1000 statistic rebuilds pending, all doing a marginal job.
        # calculate_vulnerability_statistics.si(1) | calculate_map_data.si(1)

    return group(tasks)