import logging
import time

import tldextract
from dal import autocomplete
from django import forms
from django.db import transaction
from django.db.models.functions import Lower
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from django_select2.forms import Select2TagWidget

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.scanner.http import resolves

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


# django forms are absolutely terrible. For cosmetic changes such as not showing an empty ------ in a
# RadioSelect, there is a lot of hacking, terrible answers on stackoverflow and other mismatches available
# to the point that you're working hours to fix a miniscule thing that should be trivial.
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

        self.fields['secret'] = forms.CharField(widget=forms.PasswordInput)

        self.order_fields(['team', 'secret'])

    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get("team")
        secret = cleaned_data.get("secret")

        # wait a second to deter brute force attacks (you can still do them, but good luck cracking one...)
        # 16 positions, 26 characters... each with 1 second delay. (you can of course try brute force in another
        # submit form perhaps?
        time.sleep(1)

        # it's possible NOT to select a team, in that case, don't try and validate secret.
        if team:
            try:
                team = Team.objects.all().get(id=team.id, secret=secret,
                                              allowed_to_submit_things=True, participating_in_contest=self.contest)
            except Team.DoesNotExist:
                raise ValidationError(
                    _('Incorrect secret or team. Try again!'),
                    code='invalid',
                )


class OrganisationSubmissionForm(forms.Form):

    contest = None
    team = None

    def __init__(self, *args, **kwargs):

        self.contest = kwargs.pop('contest', None)
        self.team = kwargs.pop('team', None)

        super(OrganisationSubmissionForm, self).__init__(*args, **kwargs)

    organization_name = forms.CharField(
        label="Name"
    )

    latitude = forms.DecimalField(
        max_digits=21,
        decimal_places=17,
    )

    longitude = forms.DecimalField(
        max_digits=21,
        decimal_places=17,
    )

    # "The full address of this organization, at it's current address. If there are multiple addresses, "
    # "take the one that's the most important. If they are equally important, just add them with a location"
    # "address. The points will be merged lateron."

    organization_address = forms.CharField(
        widget=forms.Textarea,
        required=True
    )

    organization_wikipedia = forms.URLField(
        label="Wikipedia page",
        help_text="Autofilled. Might be wrong. To quickly find the correct wiki page, start a search by "
                  "clicking <a href='https://en.wikipedia.org/w/index.php?search="
                  "ministry+van+binnenlandse+zaken&title=Special:Search&go=Go'>here: search wikipedia</a>.",
        required=False
    )

    organization_wikidata = forms.CharField(
        label="Wikidata code",
        help_text="Autofilled. Might be wrong. Find a Q code on <a href='https://www.wikidata.org/wiki/"
                  "Wikidata:Main_Page' target='_blank'>wikidata</a>.",
        required=False
    )

    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/'),
        label="Type / Map Layer",
        help_text="Types are rendered as separate layers on the map."
    )

    organization_evidence = forms.CharField(
        widget=forms.Textarea,
        label="Sources verifying the existence of this organization",
        required=False,
        help_text=""
    )

    # todo: clean the geolocated address to fit the rest of the system.

    def clean(self):
        # verify that an organization of this type is not in the database yet...
        cleaned_data = super().clean()
        organization_type_name = cleaned_data.get("organization_type_name")
        name = cleaned_data.get("organization_name")
        country = self.contest.target_country

        # todo: normalize the name for checking if it exists
        exists = Organization.objects.all().filter(
            type=organization_type_name, name__iexact=name, is_dead=False, country=country).exists()

        if exists:
            raise ValidationError(
                _('This organization %(organization)s already exists in the database for this type / layer.'),
                code='invalid',
                params={'organization': name},
            )

        exists = OrganizationSubmission.objects.all().filter(
            organization_type_name=organization_type_name,
            organization_name__iexact=name,
            organization_country=country).exists()

        if exists:
            raise ValidationError(
                _('This organization %(organization)s has been suggested already.'),
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
        organization_country = self.contest.target_country
        organization_name = self.cleaned_data.get('organization_name', None)
        lat = self.cleaned_data.get('latitude', None)
        lng = self.cleaned_data.get('longitude', None)
        organization_address = self.cleaned_data.get('organization_address', None)
        organization_wikipedia = self.cleaned_data.get('organization_wikipedia', None)
        organization_wikidata = self.cleaned_data.get('organization_wikidata', None)
        organization_type_name = self.cleaned_data.get('organization_type_name', None)
        organization_evidence = self.cleaned_data.get('organization_evidence', None)

        submission = OrganizationSubmission(
            added_by_team=Team.objects.get(pk=team),
            organization_address=organization_address,
            organization_evidence=organization_evidence,
            organization_name=organization_name,
            organization_type_name=organization_type_name,
            organization_wikipedia=organization_wikipedia,
            organization_wikidata_code=organization_wikidata,
            organization_address_geocoded=[lng, lat],
            organization_country=organization_country,
            added_on=timezone.now(),
            has_been_accepted=False,
            has_been_rejected=False
        )
        submission.save()

    # based on: https://www.gyford.com/phil/writing/2017/03/16/django-admin-map/
    # Loading this JS AFTER via the media options doesn't work...
    class Media:
        css = {
            'all': ('css/location_picker.css',),
        }


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
                forward=['organization_type_name', 'country']
            ),
            help_text="""
            Hints:"
                <ul>
                    <li>If you can't find the organization, try the abbreviated name.</li>
                    <li>You can also search for organization type, and it's name at the same time.</li>
                    <li>A list of all approved organizations is shown <a href='/game/submitted_organizations/'>
                    here</a></li>
                    <li>If your newly added organization is missing, please ask the competition host to verify your
                    organization.</li>
                    <li>Urls entered below will be added to all organizations selected here.</li>
                </ul>
            """
        )

        # try and inject values into the tagswidget
        valid = []
        try:
            sites = self.data.getlist('websites', [])
            incomplete, not_resolvable, valid = self.filter_websites(sites)
            # log.debug("incomplete: %s, not_resolvable: %s, valid: %s" % (incomplete, not_resolvable, valid))
            initial = valid
            choices = []
            for site in valid:
                choices.append((site, site))
                # can't add initial here, results in infinite loop
            # log.debug("things where submitted: %s" % valid)
        except AttributeError:
            # nothing was submitted
            initial = []
            choices = []

        # you'll never see an error...
        # override what is submitted (which can contain https:// / http:// with the valid sites
        # to prevent the 'Select a valid choice. https://blaat.nl is not one of the available choices.' message
        # this overrides some of the implied validation that happens in MultipleChoiceField, which doesn't
        # match the sites that are submitted, as they are filterd (seen above)
        # This is a terrible hack, which is what you get when the complexity for the control is so insanely high.
        if valid:
            self.data._mutable = True
            # have to add multiple... one each. A MultiValueDict...
            # remove all values from any websites keys, and only add the valid ones as possible data.
            self.data.pop('websites')

            for site in valid:
                # this only overwrites the first one...
                # https://kite.com/python/docs/django.http.request.QueryDict
                self.data.update({'websites': site})

        # https://github.com/applegrew/django-select2/issues/33
        # finding this took me two hours :) but it's still faster than developing it yourself.
        # The issue was the documentation was not online.

        self.fields['websites'] = forms.MultipleChoiceField(
            widget=Select2TagWidget,
            choices=choices,
            initial=initial,
            label="Addresses of Services, Websites and other online presence.",
            help_text="""
            Hints:
                <ul>
                <li>The following is all the same url (google.com):
                https://google.com, https://www.google.com, http://nonsense.google.com, bla.nonsense.google.com,
                google.com
                </li>
                <li>Subdomains and protocols are removed: the system will discover these.</li>
                <li>Each address will be resolved to see if it exists. This can take a while.</li>
                <li>You can enter multiple sites at once using comma or space as a delimiter.
                For example: The value
                <i>failmap.org, microsoft.com, apple.com </i> can be copy-pasted succesfully.</li>
                <li>The url will be added to all organizations selected above, be careful.</li>
                <li>It's not possible to enter IP addresses: the IP's behind services/organizations often change.</li>
                <li>Urls that don't resolve or are in incorrect format will be automatically removed.</li>
                </ul>
            """
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

        if incomplete and not_resolvable:
            raise ValidationError('Please review your submission and try again. '
                                  'Removed because of being incomplete addresses: '
                                  '%s. Removed because not resolvable: %s. '
                                  '' %
                                  (', '.join(incomplete), ', '.join(not_resolvable)),
                                  code='not_complete_and_not_resolvable')

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

        # clean_websites already has been called automatically...
        websites = self.data.getlist('websites', [])

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

                # only add it once to the new list :)
                if website not in new:
                    new.append(website)

        self.cleaned_data['websites'] = new

    @transaction.atomic
    def save(self):

        # validate again to prevent duplicates within the transaction
        # we can also check if the data is not in the db yet, which is nicer as it potentially saves a lot of time
        self.clean()

        organizations = self.cleaned_data.get('for_organization', None)
        websites = self.cleaned_data.get('websites', None)

        for organization in organizations:
            for website in websites:

                exists = UrlSubmission.objects.all().filter(
                    for_organization=Organization.objects.get(pk=organization),
                    url=website,
                ).exists()

                if exists:
                    continue

                submission = UrlSubmission(
                    added_by_team=Team.objects.get(pk=self.team),
                    for_organization=Organization.objects.get(pk=organization),
                    url=website,
                    added_on=timezone.now(),
                    has_been_accepted=False,
                )
                submission.save()
