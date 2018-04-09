import logging
import time

import tldextract
from dal import autocomplete
from django.contrib.gis import forms
from django.db import transaction
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.organizations.models import Organization, OrganizationType, Url
from failmap.scanners.scanner_http import resolves

# todo: callback on edit address, put result in leaflet:


log = logging.getLogger(__package__)


# todo: rewrite to get the active contest, this is a hack to prevent creating a fixture with a first value.
def get_default_contest():
    contest = Contest.objects.first()
    if contest:
        return contest
    else:
        return 0


# todo: this doesn't work yet
# don't show the secret (only in the source)
# should this be in forms.py or in admin.py?
# https://stackoverflow.com/questions/17523263/how-to-create-password-field-in-model-django
class TeamForm(forms.Form):
    field_order = ('team', 'secret')

    secret = forms.CharField(widget=forms.PasswordInput)

    team = forms.ModelChoiceField(
        widget=forms.RadioSelect,
        queryset=Team.objects.all().filter(
            allowed_to_submit_things=True, participating_in_contest=get_default_contest()),
    )

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
class OrganisationSubmissionForm(forms.ModelForm):

    # todo: filter based on country and organization type.
    # todo: but how to suggest new organizations?
    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/')
    )

    organization_name = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='/game/autocomplete/organization-autocomplete/',
                                                 forward=['organization_type_name'])
    )

    class Meta:
        model = OrganizationSubmission

        # todo: show map, view only.
        fields = ('organization_type_name', 'organization_name', 'organization_address_geocoded',)

        # widgets = {'organization_address_geocoded': GooglePointFieldWidget}


class UrlSubmissionForm(forms.Form):
    field_order = ('country', 'organization_type_name', 'for_organization', 'url',)

    country = CountryField().formfield(
        required=False
    )

    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/',
                                         forward=['country']),
        required=False
    )

    for_organization = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='/game/autocomplete/organization-autocomplete/',
                                                 forward=['organization_type_name', 'country'])
    )

    url = forms.CharField()

    def clean_url(self):
        url = self.cleaned_data['url']

        extract = tldextract.extract(url)
        if not extract.suffix:
            raise ValidationError(
                _('Invalid or missing suffix (like .com etc): %(url)s'),
                code='invalid',
                params={'url': url},
            )

        # see if the URL resolves at all:
        if not resolves(url):
            raise ValidationError(
                _('URL does not resolve (anymore): %(url)s.'),
                code='does_not_resolve',
                params={'url': url},
            )

        return url

    # clean moet NA de velden... niet VOOR de velden...
    def clean(self):

        # this is a (i think) dirty hack. The clean should be called after all fields have been validated.
        # but this is run even though there are ValidationErrors on fields.

        cleaned_data = super().clean()
        organisations = cleaned_data.get("for_organization")
        url = cleaned_data.get("url")

        if not organisations or not url:
            raise forms.ValidationError(
                "Fix the errors."
            )

        log.info(organisations)

        # todo: raise multiple validation errors, so you can delete multiple organizations in the list
        # perhaps, use the add error.
        for organization in organisations:
            if Url.objects.all().filter(url=url, organization=organization).exists():
                raise ValidationError(
                    _('This URL %(url)s is already in the production data for organization %(organization)s'),
                    code='invalid',
                    params={'url': url, 'organization': organization},
                )

        # See if the URL is already suggested for these organizations
            if UrlSubmission.objects.all().filter(url=url, for_organization=organization).exists():
                raise ValidationError(
                    _('This URL %(url)s is already suggested for organization %(organization)s'),
                    code='invalid',
                    params={'url': url, 'organization': organization},
                )

        # See if the URL already exists, for these organizations

    # todo: check if the team belongs to the contest... (elsewhere)
    @transaction.atomic
    def save(self, team):
        # validate again to prevent race conditions
        self.clean_url()
        self.clean()

        organizations = self.cleaned_data.get('for_organization', None)
        url = self.cleaned_data.get('url', None)

        # a horrible error...
        if not organizations or not url:
            raise forms.ValidationError(
                "Race condition error: while form was submitted duplicated where created. Try again to see duplicated."
            )

        for organization in organizations:
            submission = UrlSubmission(
                added_by_team=Team.objects.get(pk=team),
                for_organization=organization,
                url=url,
                added_on=timezone.now(),
                has_been_accepted=False,
            )
            submission.save()

    class Meta:
        # model = UrlSubmission  # not bound to a model, we have to write save ourselves since we want to do
        # a bit of dirty hacks (to prevent more N-N fields).

        fields = ('url', 'for_organization', )
