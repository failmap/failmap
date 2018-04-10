import logging
import time

import tldextract
from crispy_forms.bootstrap import AppendedText, FormActions, PrependedText
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Layout, Submit
from dal import autocomplete
# from django.contrib.gis import forms  # needs gdal, which...
from django import forms
from django.db import transaction
from django.db.utils import OperationalError
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
# workaround to start a contest view, has to be rewritten to use the configured default and fallback etc
def get_default_contest():
    try:
        return Contest.objects.first()
    except OperationalError:
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
class OrganisationSubmissionForm(forms.Form):
    field_order = ('organization_type_name', 'organization_name', 'organization_address', 'organization_evidence')

    # todo: filter based on country and organization type.
    # todo: but how to suggest new organizations?
    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/')
    )

    organization_name = forms.CharField()

    organization_wikipedia = forms.URLField()

    organization_address = forms.CharField(widget=forms.Textarea)

    organization_evidence = forms.CharField(widget=forms.Textarea)

    def clean(self):
        # verify that an organization of this type is not in the database yet...
        cleaned_data = super().clean()
        organization_type_name = cleaned_data.get("organization_type_name")
        name = cleaned_data.get("organization_name")

        # todo: allow adding for any country...
        # todo: this is now a setting in the contest... should be availble somewhere...
        exists = Organization.objects.all().filter(
            type=organization_type_name, name=name, is_dead=False, country='NL').exists()

        if exists:
            raise ValidationError(
                _('This organization %(organization)s already exists in the database for this group.'),
                code='invalid',
                params={'organization': name},
            )

    @transaction.atomic
    def save(self, team):
        organization_type_name = self.cleaned_data.get('organization_type_name', None)
        organization_name = self.cleaned_data.get('organization_name', None)
        organization_address = self.cleaned_data.get('organization_address', None)
        organization_evidence = self.cleaned_data.get('organization_address', None)
        organization_wikipedia = self.cleaned_data.get('organization_wikipedia', None)

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
            added_on=timezone.now(),
            has_been_accepted=False,
            has_been_rejected=False
        )
        submission.save()


class UrlSubmissionForm(forms.Form):
    field_order = ('country', 'organization_type_name', 'for_organization', 'url',)

    country = CountryField().formfield(
        required=False,
        help_text="This only helps finding the correct organization."
    )

    organization_type_name = forms.ModelChoiceField(
        queryset=OrganizationType.objects.all(),
        widget=autocomplete.ModelSelect2(url='/game/autocomplete/organization-type-autocomplete/',
                                         forward=['country']),
        required=False,
        help_text="This only helps finding the correct organization."
    )

    for_organization = forms.ModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=autocomplete.ModelSelect2Multiple(url='/game/autocomplete/organization-autocomplete/',
                                                 forward=['organization_type_name', 'country'])
    )

    url = forms.CharField(
        help_text="Do NOT enter http:// or https://"
    )

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('text_input', css_class='input-xlarge'),
        Field('textarea', rows="3", css_class='input-xlarge'),
        'radio_buttons',
        Field('checkboxes', style="background: #FAFAFA; padding: 10px;"),
        AppendedText('appended_text', '.00'),
        PrependedText('prepended_text', '<input type="checkbox" checked="checked" value="" id="" name="">',
                      active=True),
        PrependedText('prepended_text_two', '@'),
        'multicolon_select',
        FormActions(
            Submit('save_changes', 'Save changes', css_class="btn-primary"),
            Submit('cancel', 'Cancel'),
        )
    )

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

    # class Meta:
        # model = UrlSubmission  # not bound to a model, we have to write save ourselves since we want to do
        # a bit of dirty hacks (to prevent more N-N fields).

        # fields = ('url', 'for_organization', )
