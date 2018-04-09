import logging

from dal import autocomplete
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_page

from failmap.game.forms import OrganisationSubmissionForm, TeamForm, UrlSubmissionForm
from failmap.game.models import Contest, Team
from failmap.map.calculate import get_calculation
from failmap.organizations.models import Organization, OrganizationType
from failmap.scanners.models import EndpointGenericScan, TlsQualysScan

log = logging.getLogger(__package__)

one_minute = 60
one_hour = 60 * 60
one_day = 24 * 60 * 60
ten_minutes = 60 * 10


# Create your views here.
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


@cache_page(ten_minutes)
def scores(request):

    teams = Team.objects.all().filter(participating_in_contest=Contest.objects.get(id=1))

    scores = []
    for team in teams:

        # todo: je haalt nu ALLE scans op, niet de laatste per URL. Zelfde gedoe als altijd.
        # todo: maak dit wel correct.
        # Op de grote hoop zal het wel meevallen, voor het spel is het even voldoende... er zijn
        # nog weinig urls gedeeld over organisaties / samenwerkingsverbanden enzo.
        scans = list(TlsQualysScan.objects.all().filter(
            endpoint__url__urlsubmission__added_by_team=team.id,
            endpoint__url__urlsubmission__has_been_accepted=True
        ))

        scans += list(EndpointGenericScan.objects.all().filter(
            endpoint__url__urlsubmission__added_by_team=team.id,
            endpoint__url__urlsubmission__has_been_accepted=True
        ))

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

        score = {
            'team': team.name,
            'high': final_calculation['high'],
            'medium': final_calculation['medium'],
            'low': final_calculation['low'],
        }

        scores.append(score)

    # order the scores.
    scores = sorted(scores, key=lambda k: (k['high'], k['medium'], k['low']), reverse=True)

    try:
        team = Team.objects.get(pk=request.session.get('team', '-'))
    except team.DoesNotExist:
        team = {"name": "-"}

    return render(request, 'game/scores.html', {'team': team,
                                                'scores': scores})


def teams(request):

    if request.POST:
        form = TeamForm(request.POST)

        if form.is_valid():
            request.session['team'] = form.cleaned_data['team']
            form = TeamForm()

    else:
        form = TeamForm()

    return render(request, 'game/submit_team.html', {'form': form})


def submit_organisation(request):

    # validate you're in a session
    if not request.session.get('team'):
        return redirect('/game/team/')

    form = OrganisationSubmissionForm()
    return render(request, 'game/submit_organisation.html', {'form': form})


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
