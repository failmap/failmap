import logging
from datetime import datetime

import pytz
from dal import autocomplete
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import OperationalError
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page

from failmap.game.forms import ContestForm, OrganisationSubmissionForm, TeamForm, UrlSubmissionForm
from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.map.calculate import get_calculation
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.models import EndpointGenericScan, TlsQualysScan

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
one_day = 24 * 60 * 60
ten_minutes = 60 * 10


# workaround to start a contest view, has to be rewritten to use the configured default and fallback etc
def get_default_contest(request):
    try:
        if request.session['contest']:
            return Contest.objects.get(id=request.session['contest'])
        else:
            return Contest.objects.first()
    # temp supressing ALL exceptions
    # todo: make this sane again
    except (OperationalError, Exception, Contest.DoesNotExist):
        return 0


# todo: what about urls that are being added through another contest?
@login_required(login_url='/authentication/login/')
def submit_url(request):

    # validate you're in a session
    if not request.session.get('team'):
        return redirect('/game/team/')

    if request.POST:
        form = UrlSubmissionForm(request.POST)

        if form.is_valid():
            # manually saving the form, this is not your normal 1 to 1 save.
            form.save(team=request.session.get('team'))

            # don't add the URL, so you can quickly add urls to the same organization.
            # this will cause some noise, but also more entries.
            data = {
                'organization_type_name': form.cleaned_data.get('organization_type_name'),
                'country': form.cleaned_data.get('country'),
                'for_organization': form.cleaned_data.get('for_organization')
            }
            added_url = form.cleaned_data.get('url')
            form = UrlSubmissionForm(data)

            return render(request, 'game/submit_url.html', {'form': form, 'success': True,
                                                            'url': added_url})

    else:
        form = UrlSubmissionForm()

    return render(request, 'game/submit_url.html', {'form': form,
                                                    'error': form.errors})


@login_required(login_url='/authentication/login/')
def submit_organisation(request):

    # validate you're in a session
    if not request.session.get('team'):
        return redirect('/game/team/')

    if request.POST:
        form = OrganisationSubmissionForm(request.POST)

        if form.is_valid():
            # manually saving the form, this is not your normal 1 to 1 save.
            form.save(team=request.session.get('team'))

            form = OrganisationSubmissionForm()

            return render(request, 'game/submit_organisation.html', {'form': form, 'success': True})

    else:
        form = OrganisationSubmissionForm()

    return render(request, 'game/submit_organisation.html', {'form': form})


@cache_page(ten_minutes)
def scores(request):

    teams = Team.objects.all().filter(participating_in_contest=get_default_contest(request))

    scores = []
    for team in teams:

        # todo: je haalt nu ALLE scans op, niet de laatste per URL. Zelfde gedoe als altijd.
        # todo: maak dit wel correct.
        # Op de grote hoop zal het wel meevallen, voor het spel is het even voldoende... er zijn
        # nog weinig urls gedeeld over organisaties / samenwerkingsverbanden enzo. Dus het toevoegen van
        # al bestaande / gescande urls zal erg meevallen. Anders heb je mazzel.
        scans = list(TlsQualysScan.objects.all().filter(
            endpoint__url__urlsubmission__added_by_team=team.id,
            endpoint__url__urlsubmission__has_been_accepted=True
        ))

        scans += list(EndpointGenericScan.objects.all().filter(
            endpoint__url__urlsubmission__added_by_team=team.id,
            endpoint__url__urlsubmission__has_been_accepted=True
        ))

        rejected = UrlSubmission.objects.all().filter(
            added_by_team=team.id,
            has_been_rejected=True
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

        # todo: generic scans

        score_multiplier = {
            'low': 100,
            'medium': 250,
            'high': 1000,
            'rejected': 1337,
        }

        score = {
            'team': team.name,
            'high': final_calculation['high'],
            'high_multiplier': score_multiplier['high'],
            'high_score': final_calculation['high'] * score_multiplier['high'],
            'medium': final_calculation['medium'],
            'medium_multiplier': score_multiplier['medium'],
            'medium_score': final_calculation['medium'] * score_multiplier['medium'],
            'low': final_calculation['low'],
            'low_multiplier': score_multiplier['low'],
            'low_score': final_calculation['low'] * score_multiplier['low'],
            'rejected': rejected,
            'rejected_multiplier': score_multiplier['rejected'],
            'rejected_score': rejected * score_multiplier['rejected'],
            'total_score': final_calculation['high'] * score_multiplier['high'] +
            final_calculation['medium'] * score_multiplier['medium'] +
            final_calculation['low'] * score_multiplier['low'] - rejected * score_multiplier['rejected']
        }

        scores.append(score)

    # order the scores from high to low.
    scores = sorted(scores, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

    return render(request, 'game/scores.html', {'team': get_team_info(request),
                                                'scores': scores})


@cache_page(ten_minutes)
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

    expired_contests = Contest.objects.all().filter(until_moment__lt=datetime.now(pytz.utc))

    active_contests = Contest.objects.all().filter(from_moment__lt=datetime.now(pytz.utc),
                                                   until_moment__gte=datetime.now(pytz.utc))

    future_contests = Contest.objects.all().filter(from_moment__gte=datetime.now(pytz.utc))

    try:
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


@cache_page(ten_minutes)
def submitted_organizations(request):
    submitted_organizations = OrganizationSubmission.objects.all().filter(
        added_by_team__participating_in_contest=get_default_contest(request)).order_by('organization_name')

    already_known_organizations = Organization.objects.all().filter().exclude(
        id__in=submitted_organizations.values('organization_in_system'))

    return render(request, 'game/submitted_organizations.html', {
        'submitted_organizations': submitted_organizations,
        'already_known_organizations': already_known_organizations})


# todo: contest required!
@cache_page(ten_minutes)
def submitted_urls(request):
    submitted_urls = UrlSubmission.objects.all().filter(
        added_by_team__participating_in_contest=get_default_contest(request)).order_by('for_organization', 'url')

    # todo: query doesn't work yet
    # Another competition might be adding urls too.
    # todo: show all other urls for this competition filter.
    # this is an expensive query, which will break with a lot of data... todo: determine when /if it breaks.
    already_known_urls = Url.objects.all().filter().exclude(id__in=submitted_urls.values('url_in_system'))

    return render(request, 'game/submitted_urls.html', {'submitted_urls': submitted_urls,
                                                        'already_known_urls': already_known_urls})


@login_required(login_url='/authentication/login/')
def teams(request):

    if request.POST:
        form = TeamForm(request.POST, contest=get_default_contest(request))

        if form.is_valid():
            if form.cleaned_data['team']:
                request.session['team'] = form.cleaned_data['team'].id
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
    def get_queryset(self):
        # Todo: Don't forget to filter out results depending on the visitor !
        # if not self.request.user.is_authenticated():
        #     return Organization.objects.none()

        qs = Organization.objects.all()

        organization_type = self.forwarded.get('organization_type_name', None)
        country = self.forwarded.get('country', None)

        if organization_type:
            qs = qs.filter(type=organization_type)

        if country:
            qs = qs.filter(country=country)

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs


class OrganizationTypeAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):

        qs = OrganizationType.objects.all().filter()

        # country = self.forwarded.get('country', None)
        #
        # todo: this gives a carthesian product, of course. Distinct on fields not supported by sqlite...
        # so that doesn't work during development.
        # if country:
        #     qs = qs.filter(organization__country=country)

        if self.q:
            qs = qs.filter(name__istartswith=self.q)

        return qs
