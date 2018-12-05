import logging
from datetime import datetime

import pytz
import simplejson as json
import spectra
from babel import languages
from constance import config
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify

from failmap.app.common import JSEncoder
from failmap.game.forms import ContestForm, OrganisationSubmissionForm, TeamForm, UrlSubmissionForm
from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.map.calculate import get_calculation
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.models import EndpointGenericScan, UrlGenericScan
from failmap.scanners.types import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
one_day = 24 * 60 * 60
ten_minutes = 60 * 10


# workaround to start a contest view, has to be rewritten to use the configured default and fallback etc
def get_default_contest(request):
    try:
        if request.session.get('contest', 0):
            # log.debug("Returning a contest from session.")
            return Contest.objects.get(id=request.session['contest'])
        else:
            # get the first contest that is currently active, if nothing is active, get the first contest.
            try:
                # log.debug("Trying to find the earliest active contest")
                return Contest.objects.all().filter(
                    until_moment__gte=datetime.now(pytz.utc),
                    from_moment__lte=datetime.now(pytz.utc)).first()
            except ObjectDoesNotExist:
                # log.debug("Get the first contest ever")
                return Contest.objects.first()

    except (OperationalError, Contest.DoesNotExist):
        # log.debug("Fallback contest value")
        return 0


# todo: what about urls that are being added through another contest?
@login_required(login_url='/authentication/login/')
def submit_url(request):

    # validate you're in a session
    if not request.session.get('team'):
        return redirect('/game/team/')

    contest = get_default_contest(request)

    if request.POST:
        form = UrlSubmissionForm(request.POST, team=request.session.get('team'), contest=get_default_contest(request))

        if form.is_valid():
            # manually saving the form, this is not your normal 1 to 1 save.
            form.save()

            # don't add the URL, so you can quickly add urls to the same organization.
            # this will cause some noise, but also more entries.
            added_url = form.cleaned_data.get('websites')
            form = UrlSubmissionForm(team=request.session.get('team'), contest=get_default_contest(request))

            return render(request, 'game/submit_url.html', {'form': form, 'success': True,
                                                            'url': ', '.join(added_url), })

    else:
        form = UrlSubmissionForm(team=request.session.get('team'), contest=get_default_contest(request))

    return render(request, 'game/submit_url.html', {'form': form,
                                                    'error': form.errors,
                                                    'contest': contest})


@login_required(login_url='/authentication/login/')
def submit_organisation(request):

    # validate you're in a session
    if not request.session.get('team'):
        return redirect('/game/team/')

    contest = get_default_contest(request)
    language = languages.get_official_languages(contest.target_country)[0]

    if request.POST:
        form = OrganisationSubmissionForm(request.POST, team=request.session.get('team'), contest=contest)

        if form.is_valid():
            # manually saving the form, this is not your normal 1 to 1 save.
            form.save(team=request.session.get('team'))
            form = OrganisationSubmissionForm(team=request.session.get('team'), contest=contest)
            return render(request, 'game/submit_organisation.html',
                          {'form': form,
                           'success': True,
                           'GOOGLE_MAPS_API_KEY': config.GOOGLE_MAPS_API_KEY,
                           'target_country': contest.target_country,
                           'language': language
                           })

    else:
        form = OrganisationSubmissionForm(team=request.session.get('team'), contest=contest,)

    return render(request, 'game/submit_organisation.html', {'form': form,
                                                             'GOOGLE_MAPS_API_KEY': config.GOOGLE_MAPS_API_KEY,
                                                             'target_country': contest.target_country,
                                                             'language': language,
                                                             'contest': contest})


def scores(request):

    # todo: this param handling code is absolutely disgusting, it should be more beautiful.
    # todo: should we just get the last contest if there is no contest at all?
    submitted_contest = request.GET.get('contest', "")
    if submitted_contest is not None and submitted_contest.isnumeric():
        submitted_contest = int(submitted_contest)
    else:
        submitted_contest = 0

    if submitted_contest > -1:
        try:
            contest = Contest.objects.get(id=submitted_contest)
        except ObjectDoesNotExist:
            contest = get_default_contest(request)
    else:
        contest = get_default_contest(request)

    # remove disqualified teams.
    teams = Team.objects.all().filter(participating_in_contest=contest, allowed_to_submit_things=True)

    scores = []
    for team in teams:
        """
        Out of simplicity _ALL_ scores are retrieved instead of the last one per URL. Last one-per is not supported
        in Django and therefore requires a lot of code. The deviation is negligible during a contest as not so much
        will change in a day or two. On the long run it might increase the score a bit when incorrect fixes are applied
        or a new error is found. If the discovered issue is fixed it doesn't deliver additional points.
        """
        scans = list(EndpointGenericScan.objects.all().filter(
            endpoint__url__urlsubmission__added_by_team=team.id,
            endpoint__url__urlsubmission__has_been_accepted=True,
            rating_determined_on__lte=contest.until_moment,
            type__in=ENDPOINT_SCAN_TYPES
        ))

        scans += list(UrlGenericScan.objects.all().filter(
            url__urlsubmission__added_by_team=team.id,
            url__urlsubmission__has_been_accepted=True,
            rating_determined_on__lte=contest.until_moment,
            type__in=URL_SCAN_TYPES
        ))

        added_urls = UrlSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_accepted=True,
            has_been_rejected=False,
        ).count()

        added_organizations = OrganizationSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_accepted=True,
            has_been_rejected=False
        ).count()

        rejected_organizations = OrganizationSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_accepted=False,
            has_been_rejected=True,
        ).count()

        rejected_urls = UrlSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_accepted=False,
            has_been_rejected=True,
        ).count()

        final_calculation = {
            'high': 0,
            'medium': 0,
            'low': 0,
        }

        for scan in scans:
            temp_calculation = get_calculation(scan)
            final_calculation['high'] += temp_calculation['high']
            final_calculation['medium'] += temp_calculation['medium']
            final_calculation['low'] += temp_calculation['low']

        score_multiplier = {
            'low': 100,
            'medium': 250,
            'high': 1000,
            'rejected_organization': 1337,
            'rejected_url': 1337,
            'organization': 500,
            'url': 250,
        }

        # if you're too lazy to enter a color.
        # or the control doesn't work.
        if team.color:
            color = spectra.html(team.color.upper())
            # nope, deep frying doesn't help us
            # color = color.saturate(100)  # deep fry the color, so something remains even after insane brighten
            color = color.brighten(10)
            color_code = color.hexcode
        else:
            color_code = "#FFFFFF"

        score = {
            'team': team.name,
            'team_color': team.color,
            # transparency makes it lighter and more beautiful.
            'team_color_soft': "%s%s" % (color_code, '33'),
            'high': final_calculation['high'],
            'high_multiplier': score_multiplier['high'],
            'high_score': final_calculation['high'] * score_multiplier['high'],
            'medium': final_calculation['medium'],
            'medium_multiplier': score_multiplier['medium'],
            'medium_score': final_calculation['medium'] * score_multiplier['medium'],
            'low': final_calculation['low'],
            'low_multiplier': score_multiplier['low'],
            'low_score': final_calculation['low'] * score_multiplier['low'],
            'added_organizations': added_organizations,
            'added_organizations_multiplier': score_multiplier['organization'],
            'added_organizations_score': added_organizations * score_multiplier['organization'],
            'added_urls': added_urls,
            'added_urls_multiplier': score_multiplier['url'],
            'added_urls_score': added_urls * score_multiplier['url'],
            'rejected_organizations': rejected_organizations,
            'rejected_organizations_multiplier': score_multiplier['rejected_organization'],
            'rejected_organizations_score': rejected_organizations * score_multiplier['rejected_organization'],
            'rejected_urls': rejected_urls,
            'rejected_urls_multiplier': score_multiplier['rejected_url'],
            'rejected_urls_score': rejected_urls * score_multiplier['rejected_url'],
            'total_score':
                final_calculation['high'] * score_multiplier['high'] +
                final_calculation['medium'] * score_multiplier['medium'] +
                final_calculation['low'] * score_multiplier['low'] +
                added_organizations * score_multiplier['organization'] +
                added_urls * score_multiplier['url'] - (
                rejected_urls * score_multiplier['rejected_url'] +
                rejected_organizations * score_multiplier['rejected_organization']
            )
        }

        scores.append(score)

    # order the scores from high to low.
    scores = sorted(scores, key=lambda k: (k['total_score'], k['high'], k['medium'], k['low']), reverse=True)

    return render(request, 'game/scores.html', {'team': get_team_info(request),
                                                'scores': scores,
                                                'contest': contest,
                                                'menu_selected': 'scores'})


def contests(request):

    if request.POST:
        form = ContestForm(request.POST)

        if form.is_valid():
            if form.cleaned_data['id']:
                request.session['contest'] = form.cleaned_data['id']
                request.session['team'] = None  # resetting the team when switching
                return redirect('/game/team/')
            else:
                request.session['contest'] = None
    else:
        form = ContestForm()

    expired_contests = Contest.objects.all().filter(
        until_moment__lt=datetime.now(pytz.utc)
    ).annotate(
        teams=Count('team', distinct=True)
    ).annotate(
        urls=Count('team__urlsubmission')
    )

    active_contests = Contest.objects.all().filter(
        from_moment__lt=datetime.now(pytz.utc),
        until_moment__gte=datetime.now(pytz.utc)
    ).annotate(
        teams=Count('team', distinct=True)
    ).annotate(
        urls=Count('team__urlsubmission')
    )

    future_contests = Contest.objects.all().filter(
        from_moment__gte=datetime.now(pytz.utc)
    ).annotate(
        teams=Count('team', distinct=True)
    ).annotate(
        urls=Count('team__urlsubmission')
    )

    # don't select a contest if you don't have one in your session.
    contest = None
    try:
        if request.session.get("contest", 0):
            contest = get_default_contest(request)
    except Contest.DoesNotExist:
        contest = None

    return render(request, 'game/contests.html', {
        'contest': contest,
        'expired_contests': expired_contests,
        'active_contests': active_contests,
        'future_contests': future_contests,
        'error': form.errors
    })

# todo: validate organizatio type name...


def submitted_organizations(request):
    contest = get_default_contest(request)

    submitted_organizations = OrganizationSubmission.objects.all().filter(
        added_by_team__participating_in_contest=contest
    ).order_by('organization_type_name', 'organization_name')

    # not excluding the organizations submitted in this contest, as that IN filter will become too large.
    already_known_organizations = Organization.objects.all().filter(
        country=contest.target_country).select_related('type').order_by('type__name', 'name')

    return render(request, 'game/submitted_organizations.html', {
        'submitted_organizations': submitted_organizations,
        'already_known_organizations': already_known_organizations,
        'contest': get_default_contest(request)})


# todo: contest required!
def submitted_urls(request):
    """
    todo: overhaul to vue
    The result set is extremely fast, but rendering takes up a few seconds. This should be done on the client to
    save resources. This requires an overhaul of the system to Vue (as we do with the normal website).
    """
    contest = get_default_contest(request)

    submitted_urls = UrlSubmission.objects.all().filter(
        added_by_team__participating_in_contest=contest).order_by(
        'for_organization', '-added_on', 'url').select_related('added_by_team', 'for_organization', 'url_in_system')

    # sqlite, when there is a NULL in the IN query, the set is NULL and you'll get nothing back.
    # subdomains are irrellevant given contestants cannot add them.
    # the IN query will be too long, and that means exceptions. so an in query to exclude the submitted
    # urls has been removed.
    # you can see the adding date for this :)
    already_known_urls = Url.objects.all().filter(
        organization__country=contest.target_country,
        computed_subdomain="",
        organization__is_dead=False,
    ).order_by('-created_on').values('url', 'onboarding_stage', 'not_resolvable', 'organization__country',
                                     'organization__name', 'created_on')

    return render(request, 'game/submitted_urls.html',
                  {'submitted_urls': submitted_urls,
                   'already_known_urls': already_known_urls,
                   'contest': contest})


def rules_help(request):
    return render(request, 'game/rules_help.html')


@login_required(login_url='/authentication/login/')
def map(request):
    contest = get_default_contest(request)

    # also enrich with submitted urls and orgnaizations

    submitted_organizations = OrganizationSubmission.objects.all().filter(
        added_by_team__participating_in_contest=contest
    ).order_by('organization_type_name', 'organization_name')

    submitted_urls = UrlSubmission.objects.all().filter(
        added_by_team__participating_in_contest=contest).order_by(
        'for_organization', '-added_on', 'url'
    ).select_related('added_by_team', 'for_organization', 'url_in_system')

    return render(request, 'game/map.html', {
        'contest': contest,
        'team': get_team_info(request),
        'submitted_urls': submitted_urls,
        'submitted_organizations': submitted_organizations
    })


@login_required(login_url='/authentication/login/')
def contest_map_data(request):
    """
    This doesn't have to take in account the time sliding features of failmap.

    Just take ANY result from the scans matching it with the is_latest_coordinate. It's already
    linked to organization. So we should be able to get a quick result IN django.

    :param request:
    :param contest_id:
    :return:
    """

    contest = get_default_contest(request)

    data = {
        "metadata": {
            "type": "FeatureCollection",
            "render_date": datetime.now(pytz.utc),
            "data_from_time": datetime.now(pytz.utc),
            "remark": "yolo",
        },
        "crs":
            {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features":
            [

        ]
    }

    # won't i lose "last scan moment" as it overstretches the competition boundaries? Should use created on?
    # yes, use created on. If there is a new rating, there will be a scan outside of the competition bounds.

    # is the organization really prefetched? And what one really?
    # the amount of data stays relatively low given we're not adding all hundreds of subdomains that are auto discovered
    # todo: during contest, do not onboard auto-discovered subdomains, as it interferes with scans (creates too many).
    # We don't filter out only top level domains, because we might want to add some special subdomains from
    # third party service suppliers. For example: organization.thirdpartysupplier.com.
    # normal contests prohibit these subdomains.
    endpoint_scans = list(EndpointGenericScan.objects.all().filter(
        endpoint__url__urlsubmission__added_by_team__participating_in_contest=contest.pk,
        endpoint__url__urlsubmission__has_been_accepted=True,
        type__in=ENDPOINT_SCAN_TYPES,
        rating_determined_on__lte=contest.until_moment
    ).prefetch_related('endpoint__url__organization').order_by('endpoint__url__organization'))

    url_scans = list(UrlGenericScan.objects.all().filter(
        url__urlsubmission__added_by_team__participating_in_contest=contest.pk,
        url__urlsubmission__has_been_accepted=True,
        type__in=URL_SCAN_TYPES,
        rating_determined_on__lte=contest.until_moment
    ).prefetch_related('url__organization').order_by('url__organization'))

    features = []

    # organizations / urls without scans... / organizations withouts urls
    # not relevant for scores.
    bare_organizations = list(OrganizationSubmission.objects.all().filter(
        has_been_accepted=False,
        has_been_rejected=False,
        added_by_team__participating_in_contest=contest.pk
    ))
    for bare_organization in bare_organizations:
        features.append(get_bare_organization_feature(bare_organization))

    # and organizations that have been accepted, but don't have urls yet, thus no scans.
    # this is included in the fact that there is an url(or not) and no scans.
    # bare_organizations = list(OrganizationSubmission.objects.all().filter(
    #     has_been_accepted=True,
    #     organization_in_system__u_many_o_upgrade__url__isnull=True,
    #     added_by_team__participating_in_contest=contest.pk
    # ))
    # for bare_organization in bare_organizations:
    #    features.append(get_bare_organization_feature(bare_organization))

    # organizations that have been accepted, do have urls, but don't have a scan yet
    bare_organizations = list(OrganizationSubmission.objects.all().filter(
        has_been_accepted=True,
        organization_in_system__u_many_o_upgrade__urlgenericscan__isnull=True,
        organization_in_system__u_many_o_upgrade__endpoint__endpointgenericscan__isnull=True,
        added_by_team__participating_in_contest=contest.pk
    ))

    # todo: this can have the real ID, real mapping information.
    for bare_organization in bare_organizations:
        features.append(get_bare_organization_feature(bare_organization))

    # submitted url is always for a single organization, it's stored like that to reduce complexity.
    bare_urls = list(UrlSubmission.objects.all().filter(
        has_been_accepted=False,
        has_been_rejected=False,
        added_by_team__participating_in_contest=contest.pk
    ).prefetch_related('for_organization__coordinate_set'))
    features = add_bare_url_features(features, bare_urls)

    # loop over the organizations and calculate the ratings.
    # you prefetch all the related objects, which still have to be iterated... damn,
    # because now you can't simply iterate over the data.
    # you can't sort by the first organization, as the second one might be different entirely.
    # let's build the data iteratively based on organizations in the queryset.
    for scan in endpoint_scans:
        features = add_or_update_features(features, scan)

    for scan in url_scans:
        features = add_or_update_features(features, scan)

    # update string features to json type.
    # todo: make sure that there are no strings in the database, because of this uglyness
    updated_features = []
    for feature in features:
        # also check that there is something stored at all...
        if isinstance(feature['geometry']['coordinates'], str) and feature['geometry']['coordinates']:
            feature['geometry']['coordinates'] = json.loads(feature['geometry']['coordinates'])
        else:
            updated_features.append(feature)

    data["features"] = updated_features
    return JsonResponse(data, encoder=JSEncoder)


def add_or_update_features(features, scan):
    # not really memory efficient
    new_features = []

    # features are unique by organization ID.
    organizations = get_organizations(scan)

    # First check if the feature exist, if not create it.
    existing_features = []
    for organization in organizations:
        for feature in features:
            if feature.get('properties', {}).get('organization_id', None) == organization.pk:
                # todo: should also be able to add scan results here, as it exists anyway
                new_features.append(update_feature(feature, scan))
                existing_features.append(organization.pk)

    not_featured_organizations = []
    for organization in organizations:
        if organization.pk not in existing_features:
            not_featured_organizations.append(organization)

    # create new features of the organizations that don't have one yet
    for organization in not_featured_organizations:
        new_features.append(make_new_feature(organization, scan))

    # copy the features that where not relevant to this scan
    for feature in features:
        if feature['properties']['organization_id'] not in existing_features:
            new_features.append(feature)

    return new_features


def update_feature(feature, scan):
    # log.debug('Updating feature %s, with scan %s' % (feature['properties']['organization_id'], scan))
    calculation = get_calculation(scan)

    feature['properties']['high'] += calculation['high']
    feature['properties']['medium'] += calculation['medium']
    feature['properties']['low'] += calculation['low']

    color = "red" if feature['properties']['high'] else "orange" if feature['properties'][
        'medium'] else "yellow" if feature['properties']['low'] else "green"

    feature['properties']['color'] = color

    return feature


def get_bare_organization_feature(submitted_organization):
    return {
        "type": "Feature",
        "properties":
            {
                # can't use ID of submission, because this does not match per call.
                "organization_id": "pending_%s" % submitted_organization.organization_type_name,
                "organization_type": submitted_organization.organization_type_name,
                "organization_name": submitted_organization.organization_name,
                "organization_slug": slugify(submitted_organization.organization_name),
                "overall": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "data_from": 0,
                "color": "pending",
                "total_urls": 0,
                "high_urls": 0,
                "medium_urls": 0,
                "low_urls": 0,
                "origin": "get_bare_organization_feature"
            },
        "geometry":
            {
                "type": "Point",  # nothing else supported yet, as entering coordinates is hard enough already
                # Sometimes the data is a string, sometimes it's a list. The admin
                # interface might influence this.
                "coordinates": submitted_organization.organization_address_geocoded
            }
    }


def add_bare_url_features(features, submitted_urls):

    # submitted url is always for a single organization.
    for submitted_url in submitted_urls:
        # as the submitted urls doesn't have ratings etc, we only check if we need to add the organization
        # to the list of features.

        # check if the organization is not yet in the list of features.
        if organization_in_features(submitted_url.for_organization, features):
            continue

        # take into account that some contests / urls could not associated with a region. If there is no region
        # attached to it, there is also nothing to plot, thus return the existing features
        if not submitted_url.for_organization.coordinate_set.count():
            continue

        # get the last known coordinate from this set. They are (usually) ordered by date. But it doesn't matter much
        # as it's more an indication than that it actually needs to be true/
        coordinate = submitted_url.for_organization.coordinate_set.last()
        geojsontype = coordinate.geojsontype
        area = coordinate.area

        feature = {
            "type": "Feature",
            "properties":
                {
                    "organization_id": "%s" % submitted_url.for_organization.pk,
                    "organization_type": submitted_url.for_organization.type.name,
                    "organization_name": submitted_url.for_organization.name,
                    "organization_slug": slugify(submitted_url.for_organization.name),
                    "overall": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "data_from": 0,
                    "color": "pending",
                    "total_urls": 0,
                    "high_urls": 0,
                    "medium_urls": 0,
                    "low_urls": 0,
                    "origin": "add_bare_url_features"
                },
            "geometry":
                {
                    "type": geojsontype,
                    # Sometimes the data is a string, sometimes it's a list. The admin
                    # interface might influence this.
                    "coordinates": area
                }
        }

        features.append(feature)
    return features


def organization_in_features(organization, features):
    id = str(organization.pk)  # stored as string in the feature

    for feature in features:
        if feature['properties']['organization_id'] == id:
            return True

    # not in there
    return False


def make_new_feature(organization, scan):
    # log.debug('Making new feature %s, with scan %s' % (organization, scan))

    calculation = get_calculation(scan)
    color = "red" if calculation['high'] else "orange" if calculation['medium'] else "yellow" if calculation[
        'low'] else "green"

    from failmap.organizations.models import Coordinate

    # only one multipoint or multipolygon. Unfortunately one query per organization :((((((((((((
    coordinate = Coordinate.objects.all().filter(organization=organization).order_by('-created_on').first()

    # early contest didn't require the pinpointing of a location, later contests an organization is always required
    if not coordinate:
        area = ""
        geojsontype = ""
    else:
        area = coordinate.area
        geojsontype = coordinate.geojsontype

    return {
        "type": "Feature",
        "properties":
            {
                "organization_id": organization.pk,
                "organization_type": organization.type.name,
                "organization_name": organization.name,
                "organization_slug": slugify(organization.name),
                "overall": 0,
                "high": calculation['high'],
                "medium": calculation['medium'],
                "low": calculation['low'],
                "data_from": scan.last_scan_moment,
                "color": color,
                "total_urls": 0,  # = 100%
                "high_urls": 0,
                "medium_urls": 0,
                "low_urls": 0,
                "origin": "make_new_feature"
            },
        "geometry":
            {
                "type": geojsontype,
                # Sometimes the data is a string, sometimes it's a list. The admin
                # interface might influence this.
                "coordinates": area
            }
    }


def get_organizations(scan):
    if scan.type in ENDPOINT_SCAN_TYPES:
        return scan.endpoint.url.organization.all()
    if scan.type in URL_SCAN_TYPES:
        return scan.url.organization.all()


@login_required(login_url='/authentication/login/')
def teams(request):

    # if you don't have a contest selected, you're required to do so...
    # contest 0 can exist. ?
    if request.session.get('contest', -1) < 0:
        return redirect('/game/contests/')

    if request.POST:
        form = TeamForm(request.POST, contest=get_default_contest(request))

        if form.is_valid():
            if form.cleaned_data['team']:
                request.session['team'] = form.cleaned_data['team'].id
                return redirect('/game/scores/')
            else:
                request.session['team'] = None

            request.session.modified = True
            request.session.save()
            form = TeamForm(initial={'team': get_team_id(request)}, contest=get_default_contest(request))

    else:
        form = TeamForm(initial={'team': get_team_id(request)}, contest=get_default_contest(request))

    return render(request, 'game/team.html', {'form': form, 'team': get_team_info(request)})


def get_team_id(request):
    try:
        team = Team.objects.get(pk=request.session.get('team', 0))
    except (ObjectDoesNotExist, ValueError):
        team = {"id": "-"}
    return team


def get_team_info(request):
    try:
        team = Team.objects.get(pk=request.session.get('team', 0))
    except (ObjectDoesNotExist, ValueError):
        team = {"name": "-"}
    return team


class OrganizationAutocomplete(autocomplete.Select2QuerySetView):

    # allow a bit of scrolling
    paginate_by = 100

    def get_queryset(self):

        qs = Organization.objects.all().filter(is_dead=False).order_by(Lower('name'))

        organization_type = self.forwarded.get('organization_type_name', None)
        country = self.forwarded.get('country', None)

        if organization_type:
            qs = qs.filter(type=organization_type)

        if country:
            qs = qs.filter(country=country)

        """
        Do not search on a single character, it will give too many results. Two characters is a minimum.
        """
        if not self.q or len(self.q) < 3:
            return qs

        """
        You can also search for organization type, which helps if you know the object is of a certain type.
        It even supports multiple words, if you have a space, each word will be searched for. Up to three words...
        """
        if len(self.q.split(" ")) < 4:
            for query in self.q.split(" "):
                qs = qs.filter(Q(name__icontains=query) | Q(type__name__icontains=query))
        else:
            qs = qs.filter(name__icontains=self.q)

        return qs


class OrganizationTypeAutocomplete(autocomplete.Select2QuerySetView):

    paginate_by = 100

    def get_queryset(self):

        qs = OrganizationType.objects.all().filter().order_by('name')

        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs
