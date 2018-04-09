from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from djgeojson.fields import GeoJSONField

from failmap.organizations.models import Organization, Url

# Highest level adding:

# We're going to match things that exist already, we're not going to code an entire admin interface?


class Contest(models.Model):
    name = models.CharField(
        verbose_name=_("Contest name"),
        max_length=42,
        help_text="Whatever name the team wants. Must be at least PEGI 88."
    )

    logo_filename = models.CharField(
        max_length=255,
        help_text="A nice filename for contest logos."
    )

    website = models.CharField(
        max_length=255,
        help_text="Whatever name the team wants. Must be at least PEGI 88."
    )

    from_moment = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Moment the compo opens."
    )

    until_moment = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Moment the compo closes."
    )

    target_country = CountryField(
        help_text="The country (if any) under which submissions fall."
    )

    class Meta:
        verbose_name = _('contest')
        verbose_name_plural = _('contests')

    def __str__(self):
        return "%s" % self.name


class Team(models.Model):
    """
    These are managed by the admin interface in the first version.

    """
    name = models.CharField(
        verbose_name=_("Team name"),
        max_length=42,
        help_text="Whatever name the team wants. Must be at least PEGI 88."
    )

    secret = models.CharField(
        max_length=42,
        help_text="A secret that allows them to add URLS under their team (for scoring purposes)"
    )

    participating_in_contest = models.ForeignKey(
        Contest,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    allowed_to_submit_things = models.BooleanField(
        default=False,
        help_text="Disables teams from submitting things."
    )

    class Meta:
        verbose_name = _('team')
        verbose_name_plural = _('teams')

    def __str__(self):
        return "%s/%s" % (self.participating_in_contest, self.name)


class OrganizationSubmission(models.Model):

    organization_country = CountryField()

    added_by_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    # Organization types are managed by the admin, so informed decisions are made.
    # the type is not really important, that will be managed anyway. It's more a suggestion.
    organization_type_name = models.CharField(
        max_length=42,
        default="unknown",
        help_text="The contest the team is participating in."
    )

    # the name should translate to the natural key of an existing (or a new) organization.
    # organizations can be created in the admin interface
    organization_name = models.CharField(
        max_length=42,
        default="unknown",
        help_text="The contest the team is participating in."
    )

    organization_address = models.CharField(
        max_length=600,
        default="unknown",
        help_text="The address of the (main location) of the organization. This will be used for geocoding."
    )

    organization_evidence = models.CharField(
        max_length=600,
        default="unknown",
        help_text="Sources of information about this organization."
    )

    organization_address_geocoded = GeoJSONField(
        max_length=5000,
        null=True,
        blank=True,
        help_text="Automatic geocoded organization address."
    )

    organisation_in_system = models.ForeignKey(
        Organization,
        null=True,
        help_text="This reference will be used to calculate the score and to track imports.",
        blank=True,
        on_delete=models.CASCADE
    )

    has_been_accepted = models.BooleanField(
        default=False,
        help_text="If the admin likes it, they can accept the submission to be part of the real system"
    )

    has_been_rejected = models.BooleanField(
        default=False,
        help_text="Nonsense organizations can be rejected."
    )

    added_on = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Automatically filled when creating a new submission."
    )

    def __str__(self):
        if self.has_been_accepted:
            return "OK: %s" % self.organization_name
        else:
            return self.organization_name

    class Meta:
        verbose_name = _('organisation submission')
        verbose_name_plural = _('organisation submissions')


class UrlSubmission(models.Model):
    """
    Submissions are suggestions of urls to add. They are not directly added to the system.
    The admin of the system is the consensus algorithm.

    The admin can do "imports" on these submissions if they think it's a good one.
    Todo: create admin action.

    """

    added_by_team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    for_organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    url = models.CharField(
        max_length=500,
        help_text="The URL the team has submitted, for review before acceptance."
    )

    url_in_system = models.ForeignKey(
        Url,
        null=True,
        help_text="This reference will be used to calculate the score and to track imports.",
        blank=True,
        on_delete=models.CASCADE
    )

    has_been_accepted = models.BooleanField(
        default=False,
        help_text="If the admin likes it, they can accept the submission to be part of the real system"
    )

    has_been_rejected = models.BooleanField(
        default=False,
        help_text="Rejected urls makes for deduction in points."
    )

    added_on = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Automatically filled when creating a new submission."
    )

    def __str__(self):
        if self.has_been_accepted:
            return "OK: %s" % self.url
        else:
            return self.url

    class Meta:
        verbose_name = _('url submission')
        verbose_name_plural = _('url submissions')
