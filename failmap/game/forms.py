import logging
import time

import tldextract
from dal import autocomplete
# from django.contrib.gis import forms  # needs gdal, which...
from django import forms
from django.db import transaction
from django.db.models.functions import Lower
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django_countries.widgets import CountrySelectWidget
from django_select2.forms import Select2TagWidget
from mapwidgets.widgets import GooglePointFieldWidget

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.scanner.http import resolves

# todo: callback on edit address, put result in leaflet:


log = logging.getLogger(__package__)


class ContestForm(forms.Form):
    field_order = ('id', )

    id = forms.IntegerField()

    def clean(self):
        cleaned_data = super().clean()
        id = cleaned_data.get("id")

        if not Contest.objects.all().filter(pk=id).exists():
            raise ValidationError(_('This contest does not exist.'), code='invalid',)

        """
        We don't care if it's expired, as long as you cannot add things to expired contests it's fine. Some people that
        joined a previous compo might still have the value set anyway and we're not going to validate the contest the
        user is in on every request (or smart places).
        """
        # has_expired = Contest.objects.all().filter(pk=id, until_moment__lte=datetime.now(pytz.utc))
        # if has_expired:
        #     raise ValidationError(_('This contest is already over, you cannot participate in it anymore.'),
        #                           code='invalid', )


# todo: this doesn't work yet
# don't show the secret (only in the source)
# should this be in forms.py or in admin.py?
# https://stackoverflow.com/questions/17523263/how-to-create-password-field-in-model-django
class TeamForm(forms.Form):

    contest = Contest()

    def __init__(self, *args, **kwargs):
        self.contest = kwargs.pop('contest', 0)
        super(TeamForm, self).__init__(*args, **kwargs)
        self.fields['team'] = forms.ModelChoiceField(
            widget=forms.RadioSelect,
            queryset=Team.objects.all().filter(
                allowed_to_submit_things=True, participating_in_contest=self.contest),
        )

    field_order = ('team', 'secret')

    secret = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get("team")
        secret = cleaned_data.get("secret")

        # validate secret, add some timing...
        time.sleep(1)  # wait a second to deter brute force attacks (you can still do them)

        # it's possible NOT to select a team, in that case, don't try and validate secret.
        if team:
            try:
                team = Team.objects.all().get(id=team.id, secret=secret)
            except Team.DoesNotExist:
                raise ValidationError(
                    _('Incorrect secret or team. Try again!'),
                    code='invalid',
                )

    # class Meta:
        # model = UrlSubmission  # not bound to a model, we have to write save ourselves since we want to do
        # a bit of dirty hacks (to prevent more N-N fields).

        # fields = ('team', 'secret', )


# http://django-autocomplete-light.readthedocs.io/en/master/tutorial.html
class OrganisationSubmissionForm(forms.Form):

    contest = None
    team = None

    def __init__(self, *args, **kwargs):

        self.contest = kwargs.pop('contest', None)
        self.team = kwargs.pop('team', None)

        super(OrganisationSubmissionForm, self).__init__(*args, **kwargs)

    field_order = ('organization_country', 'organization_type_name', 'organization_name',
                   'organization_address_geocoded', 'organization_address',
                   'organization_evidence')

    organization_country = CountryField().formfield(
        label="Country",
        widget=CountrySelectWidget(),
        initial="NL"
    )

    # todo: filter based on country and organization type.
    # todo: but how to suggest new organizations?
    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/'),
        label="Type"
    )

    organization_name = forms.CharField(
        label="Name"
    )

    organization_address_geocoded = forms.CharField(
        widget=GooglePointFieldWidget,
        label="Address"
    )

    organization_address = forms.CharField(
        widget=forms.Textarea
    )

    organization_evidence = forms.CharField(
        widget=forms.Textarea,
        label="Sources verifying the existence of this organization"
    )

    organization_wikipedia = forms.URLField(
        label="Wikipedia page",
        help_text="To quickly find the correct wiki page, start a search by "
                  "clicking <a href='https://en.wikipedia.org/w/index.php?search="
                  "ministry+van+binnenlandse+zaken&title=Special:Search&go=Go'>here: search wikipedia</a>."
    )

    organization_wikidata = forms.CharField(
        label="Wikidata code",
        help_text="Find a Q code on <a href='https://www.wikidata.org/wiki/"
                  "Wikidata:Main_Page' target='_blank'>wikidata</a>."
    )

    # todo: clean the geolocated address to fit the rest of the system. The ugly
    # POINT -() etc has to be formatted according our normal layout so it can be processed in the admin
    # interface.

    def clean(self):
        # verify that an organization of this type is not in the database yet...
        cleaned_data = super().clean()
        organization_type_name = cleaned_data.get("organization_type_name")
        name = cleaned_data.get("organization_name")
        country = cleaned_data.get("organization_country")

        exists = Organization.objects.all().filter(
            type=organization_type_name, name=name, is_dead=False, country=country).exists()

        if exists:
            raise ValidationError(
                _('This organization %(organization)s already exists in the database for this group.'),
                code='invalid',
                params={'organization': name},
            )

        # team not participating in contest
        if not Team.objects.all().filter(pk=self.team, participating_in_contest=self.contest).exists():
            raise ValidationError("This team does not participate in this contest.")

        # check if the contest is expired
        if timezone.now() > self.contest.until_moment:
            raise ValidationError("This contest has expired. You can't submit anything anymore. Too bad.")

    @transaction.atomic
    def save(self, team):
        organization_country = self.cleaned_data.get('organization_country', None)
        organization_type_name = self.cleaned_data.get('organization_type_name', None)
        organization_name = self.cleaned_data.get('organization_name', None)
        organization_address = self.cleaned_data.get('organization_address', None)
        organization_evidence = self.cleaned_data.get('organization_address', None)
        organization_wikipedia = self.cleaned_data.get('organization_wikipedia', None)
        organization_wikidata = self.cleaned_data.get('organization_wikidata', None)
        organization_address_geocoded = self.cleaned_data.get('organization_address_geocoded', None)

        if not all([organization_name, organization_type_name, organization_address, organization_evidence]):
            raise forms.ValidationError(
                "Missing some fields..."
            )

        submission = OrganizationSubmission(
            added_by_team=Team.objects.get(pk=team),
            organization_address=organization_address,
            organization_evidence=organization_evidence,
            organization_name=organization_name,
            organization_type_name=organization_type_name,
            organization_wikipedia=organization_wikipedia,
            organization_wikidata_code=organization_wikidata,
            organization_address_geocoded=organization_address_geocoded,
            organization_country=organization_country,
            added_on=timezone.now(),
            has_been_accepted=False,
            has_been_rejected=False
        )
        submission.save()


class UrlSubmissionForm(forms.Form):

    contest = None
    team = None

    def __init__(self, *args, **kwargs):

        self.contest = kwargs.pop('contest', None)
        self.team = kwargs.pop('team', None)

        super(UrlSubmissionForm, self).__init__(*args, **kwargs)

        self.fields['for_organization'] = forms.ModelMultipleChoiceField(
            label="Organizations",
            queryset=Organization.objects.all().filter(country=self.contest.target_country, is_dead=False
                                                       ).order_by(Lower('name')),
            widget=autocomplete.ModelSelect2Multiple(
                url='/game/autocomplete/organization-autocomplete/',
                forward=['organization_type_name', 'country']),
            help_text="Hints:"
                      "<ul>"
                      "<li>If you can't find the organization, try the abbreviated name.</li>"
                      "<li>You can also search for organization type, and it's name at the same time.</li>"
                      "<li>A list of all approved organizations is shown <a href='/game/submitted_organizations/'>"
                      "here</a></li>"
                      "<li>If your newly added organization is missing, please ask the competition host to verify your "
                      "organization.</li>"
                      "<li>Urls entered below will be added to all organizations selected here.</li>"
                      "</ul>"
        )

        # try and inject values into the tagswidget
        try:
            sites = self.data.getlist('websites', [])
            incomplete, not_resolvable, valid = self.filter_websites(sites)
            # log.debug("incomplete: %s, not_resolvable: %s, valid: %s" % (incomplete, not_resolvable, valid))
            initial = valid
            choices = []
            for site in valid:
                choices.append((site, site))
            # log.debug("things where submitted: %s" % valid)
        except AttributeError:
            # nothing was submitted
            initial = []
            choices = []

        def getChoices():
            return [("a", "a"), ('repelsteeltje', 'repelsteeltje'), ('elger.nl', 'elger.nl')]

        # https://github.com/applegrew/django-select2/issues/33
        # finding this took me two hours :) but it's still faster than developing it yourself.
        # The issue was the documentation was not online.

        self.fields['websites'] = forms.MultipleChoiceField(
            widget=Select2TagWidget,
            choices=choices,
            initial=initial,
            label="Addresses of Services, Websites and other online presence.",
            help_text="Hints:"
                      "<ul>"
                      "<li>You can enter multiple sites at once using comma or space as a delimiter. "
                      "Example: The value "
                      "<i>failmap.org, microsoft.com, apple.com </i> should by copy-pasting.</li>"
                      "<li>The url will be added to all organizations selected above, be careful.</li>"
                      "<li>It's not possible to enter IP addresses, as the IP's behind services/organizations "
                      "often change.</li>"
                      "<li>Urls that don't resolve or are in incorrect format will be automatically removed.</li>"
                      "</ul>",
        )

        # Helps Django Autocomplete light with selecting the right autocompleted values.
        self.fields['country'] = CountryField().formfield(
            label="🔍 Filter organization by country",
            required=False,
            help_text="This only helps finding the correct organization.",
            initial=self.contest.target_country,
            widget=forms.HiddenInput()
        )

    """
    The organization type name should be obvious from the object description. This was disabled due to the extra
    query.

    organization_type_name = forms.ModelChoiceField(
        label="🔍 Filter organization by organization type",
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/',
                                         forward=['country']),
        required=False,
        help_text="This only helps finding the correct organization."
    )
    """

    @staticmethod
    def filter_websites(sites):
        incomplete = []
        not_resolvable = []
        valid = []

        for url in sites:
            url = url.replace("https://", "")
            url = url.replace("http://", "")

            extract = tldextract.extract(url)
            if not extract.suffix:
                incomplete.append(url)
                continue

            # tld extract has also removed ports, usernames, passwords and other nonsense.
            url = "%s.%s" % (extract.domain, extract.suffix)

            # see if the URL resolves at all:
            if not resolves(url):
                not_resolvable.append(url)
                continue

            valid.append(url)

        return incomplete, not_resolvable, valid

    def clean_websites(self):
        try:
            sites = self.data.getlist('websites', [])
            incomplete, not_resolvable, valid = self.filter_websites(sites)
        except AttributeError:
            # nothing submitted
            incomplete, not_resolvable, valid = [], [], []

        if incomplete:
            raise ValidationError('The following websites are not complete and have been removed: '
                                  '%s. Please review your submission and try again.' % incomplete, code='not_complete')

        if not_resolvable:
            raise ValidationError('The following sites are not resolvable and have been removed: %s. '
                                  'Please review your submission and try again.'
                                  % not_resolvable,
                                  code='not_resolvable')

        return valid

    def clean_for_organization(self):
        if not self.contest:
            raise ValidationError('You\'re not in a contest', 'no_contest')

        # mandatory check is done elsewhere.
        # You'll be getting a list of numbers.
        try:
            organizations = self.data.getlist('for_organization', [])
        except AttributeError:
            organizations = []

        existing = []

        log.debug('organizations: %s', organizations)

        for organization in organizations:
            if not Organization.objects.filter(pk=organization,
                                               country=self.contest.target_country, is_dead=False).exists():
                continue
            else:
                existing.append(organization)

        if not existing:
            raise forms.ValidationError('No existing organizations selected. ALl non-existing organizations have been'
                                        'filtered out of below input to save you some time.')

        return existing

    def clean(self):
        try:
            organizations = self.data.getlist('for_organization', [])
        except AttributeError:
            organizations = []

        websites = self.clean_websites()

        if not organizations:
            raise forms.ValidationError("Organization missing!")

        if not websites:
            raise forms.ValidationError("Websites missing!")

        # team not participating in contest
        if not Team.objects.all().filter(pk=self.team, participating_in_contest=self.contest).exists():
            raise ValidationError("This team does not participate in this contest.")

        # check if the contest is expired
        if timezone.now() > self.contest.until_moment:
            raise ValidationError("This contest has expired. You can't submit anything anymore. Too bad.")

        new = []
        for organization in organizations:
            for website in websites:

                if Url.objects.all().filter(url=website, organization=organization).exists():
                    # This URL %(url)s is already in the production data for organization %(organization)s
                    continue

                if UrlSubmission.objects.all().filter(url=website, for_organization=organization).exists():
                    # This URL %(url)s is already suggested for organization %(organization)s
                    continue

                new.append(website)

        self.cleaned_data['websites'] = new

    @transaction.atomic
    def save(self):

        # validate again to prevent duplicates
        self.clean_websites()
        self.clean()

        organizations = self.cleaned_data.get('for_organization', None)
        websites = self.cleaned_data.get('websites', None)

        log.debug('adding new')
        log.debug('organizations: %s', organizations)
        log.debug('websites: %s', websites)

        for organization in organizations:
            for website in websites:

                submission = UrlSubmission(
                    added_by_team=Team.objects.get(pk=self.team),
                    for_organization=Organization.objects.get(pk=organization),
                    url=website,
                    added_on=timezone.now(),
                    has_been_accepted=False,
                )
                submission.save()
