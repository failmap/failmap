import logging
from datetime import datetime

import pytz
from babel import languages
from constance import config
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.db.utils import OperationalError
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page

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
                                                            'url': added_url, })

    else:
        form = UrlSubmissionForm(team=request.session.get('team'), contest=get_default_contest(request))

    return render(request, 'game/submit_url.html', {'form': form,
                                                    'error': form.errors})


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
                                                             'language': language})


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
            type__in=ENDPOINT_SCAN_TYPES
        ))

        scans += list(UrlGenericScan.objects.all().filter(
            url__urlsubmission__added_by_team=team.id,
            url__urlsubmission__has_been_accepted=True,
            type__in=URL_SCAN_TYPES
        ))

        added_urls = UrlSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_accepted=True,
            has_been_rejected=False
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

        score = {
            'team': team.name,
            'team_color': team.color,
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
    scores = sorted(scores, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

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

    already_known_organizations = Organization.objects.all().filter(country=contest.target_country).exclude(
        id__in=submitted_organizations.values('organization_in_system').filter(organization_in_system__isnull=False)
    ).select_related('type').order_by('type__name', 'name')

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
        'for_organization', 'url').select_related('added_by_team', 'for_organization', 'url_in_system')

    # sqlite, when there is a NULL in the IN query, the set is NULL and you'll get nothing back.
    already_known_urls = Url.objects.all().filter(organization__country=contest.target_country).exclude(
        id__in=submitted_urls.values('url_in_system').filter(url_in_system__isnull=False)
    ).order_by('url')  # No join / cartesian product for us :( .select_related('organization')

    return render(request, 'game/submitted_urls.html',
                  {'submitted_urls': submitted_urls,
                   'already_known_urls': already_known_urls,
                   'contest': contest})


@cache_page(ten_minutes)
def rules_help(request):
    return render(request, 'game/rules_help.html')


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
