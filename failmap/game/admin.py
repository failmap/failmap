import logging

from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.organizations.models import Coordinate, Organization, OrganizationType, Url

log = logging.getLogger(__package__)


class TeamInline(CompactInline):
    model = Team
    extra = 0
    can_delete = False
    ordering = ["name"]


class OrganizationSubmissionInline(CompactInline):
    model = OrganizationSubmission
    extra = 0
    can_delete = False
    ordering = ["organization_name"]


@admin.register(Contest)
class ContestAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'target_country', 'from_moment', 'until_moment')
    search_fields = ('name', 'target_country')
    list_filter = ('name', 'target_country')

    fieldsets = (
        (None, {
            'fields': ('name', 'from_moment', 'until_moment')
        }),
        ('Configuration', {
            'fields': ('target_country', 'logo_filename'),
        }),
    )

    inlines = [TeamInline]


# todo: submissioninline, read only... there are going to be MANY new things...
@admin.register(Team)
class TeamAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'color', 'participating_in_contest', 'allowed_to_submit_things')
    search_fields = ('name', 'participating_in_contest__name')
    list_filter = ('name', 'participating_in_contest__name', 'participating_in_contest__target_country')

    fieldsets = (
        (None, {
            'fields': ('name', 'color', 'participating_in_contest', 'allowed_to_submit_things')
        }),
        ('secret', {
            'fields': ('secret', ),
        }),
    )

    inlines = [OrganizationSubmissionInline]


@admin.register(UrlSubmission)
class UrlSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('added_by_team', 'for_organization', 'url', 'has_been_accepted', 'has_been_rejected', 'added_on')
    search_fields = ('added_by_team__name', 'organization_name', 'url')

    list_filter = ('has_been_accepted', 'has_been_rejected',
                   'added_by_team__name', 'added_by_team__participating_in_contest__name')

    fields = ('added_by_team', 'for_organization', 'url', 'url_in_system', 'has_been_accepted', 'added_on')

    ordering = ('for_organization', 'url')

    actions = []

    @transaction.atomic
    def accept(self, request, queryset):
        for urlsubmission in queryset:

            # don't add the same thing over and over, allows to re-select the ones already added without a problem
            # once rejected, can't be accepted via buttons: needs to be a manual action
            if urlsubmission.has_been_accepted or urlsubmission.has_been_rejected:
                continue

            # it's possible that the url already is in the system. If so, tie that to the submitted organization.
            try:
                url = Url.objects.all().get(url=urlsubmission.url)
            except Url.DoesNotExist:
                # if it already exists, then add the url to the organization.
                url = Url(url=urlsubmission.url)
                url.save()

            # the organization is already inside the submission and should exist in most cases.
            try:
                url.organization.add(urlsubmission.for_organization)
                url.save()
            except Exception as e:
                log.error(e)

            # add some tracking data to the submission
            urlsubmission.url_in_system = url
            urlsubmission.has_been_accepted = True
            urlsubmission.save()

        self.message_user(request, "Urls have been accepted and added to the system.")
    accept.short_description = "✅  Accept"
    actions.append('accept')

    @transaction.atomic
    def reject(self, request, queryset):
        for urlsubmission in queryset:
            urlsubmission.has_been_rejected = True
            urlsubmission.save()

        self.message_user(request, "Urls have been rejected.")
    reject.short_description = "❌  Reject"
    actions.append('reject')


@admin.register(OrganizationSubmission)
class OrganizationSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('added_by_team', 'organization_name', 'has_been_accepted', 'has_been_rejected', 'added_on')
    search_fields = ('added_by_team__name', 'organization_name', 'organization_type_name')

    list_filter = ('added_by_team__name', 'has_been_accepted', 'has_been_rejected',
                   'added_by_team__participating_in_contest__name')

    fields = ('added_by_team', 'organization_country', 'organization_type_name', 'organization_name',
              'organization_address', 'organization_address_geocoded', 'organization_wikipedia',
              'organization_wikidata_code', 'has_been_accepted',
              'has_been_rejected', 'organization_in_system', 'added_on',)

    actions = []

    @transaction.atomic
    def accept(self, request, queryset):
        for osm in queryset:

            # don't add the same thing over and over, allows to re-select the ones already added without a problem
            # once rejected, can't be accepted via buttons: needs to be a manual action
            if osm.has_been_accepted or osm.has_been_rejected:
                continue

            try:
                # this might revive some old organizations, so domain knowledge is required.
                # In this case the organization already exists with the same name, type and alive.
                # this means we don't need to add a new one, or with new coordinates.
                Organization.objects.all().get(
                    name=osm.organization_name,
                    country=osm.organization_country,
                    is_dead=False,
                    type=OrganizationType.objects.get(name=osm.organization_type_name))
            except Organization.DoesNotExist:
                # Create a new one
                # address and evidence are saved elsewhere. Since we have a reference we can auto-update after
                # geocoding works. In the hopes some quality data has been added, which can be checked more easy then
                # adding this data in the system again(?)
                new_org = Organization(
                    name=osm.organization_name,
                    country=osm.organization_country,
                    is_dead=False,
                    type=OrganizationType.objects.get(name=osm.organization_type_name),
                    created_on=timezone.now(),
                )
                new_org.save()

                # of course it has a new coordinate
                new_coordinate = Coordinate(
                    organization=new_org,
                    geojsontype="Point",
                    area=osm.organization_address_geocoded,
                    edit_area=osm.organization_address_geocoded,
                    created_on=timezone.now(),
                    creation_metadata="Accepted organization submission"
                )
                new_coordinate.save()

                # and save tracking information
                osm.organization_in_system = new_org
                osm.has_been_accepted = True
                osm.save()

        self.message_user(request, "Organizations have been accepted and added to the system.")
    accept.short_description = "✅  Accept"
    actions.append('accept')

    @transaction.atomic
    def reject(self, request, queryset):
        for organizationsubmission in queryset:
            organizationsubmission.has_been_rejected = True
            organizationsubmission.save()

        self.message_user(request, "Organisation(s) have been rejected.")
    reject.short_description = "❌  Reject"
    actions.append('reject')
