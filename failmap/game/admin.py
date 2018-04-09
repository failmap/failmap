import logging

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline

from failmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from failmap.organizations.models import Url

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


# Register your models here.
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
class TeamAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'participating_in_contest', 'allowed_to_submit_things')
    search_fields = ('name', 'participating_in_contest__name')
    list_filter = ('name', 'participating_in_contest__name', 'participating_in_contest__target_country')

    fieldsets = (
        (None, {
            'fields': ('name', 'participating_in_contest', 'allowed_to_submit_things')
        }),
        ('secret', {
            'fields': ('secret', ),
        }),
    )

    inlines = [OrganizationSubmissionInline]


class UrlSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('added_by_team', 'for_organization', 'url', 'has_been_accepted', 'has_been_rejected', 'added_on')
    search_fields = ('added_by_team__name', 'organization_name', 'url')

    list_filter = ('has_been_accepted', 'has_been_rejected',
                   'added_by_team__name', 'added_by_team__participating_in_contest__name')

    fields = ('added_by_team', 'for_organization', 'url', 'url_in_system', 'has_been_accepted', 'added_on')

    ordering = ('for_organization', 'url')

    actions = []

    def accept(self, request, queryset):
        for urlsubmission in queryset:

            # don't add the same thing over and over, allows to re-select the ones already added without a problem
            # once rejected, can't be accepted via buttons: needs to be a manual action
            if urlsubmission.has_been_accepted or urlsubmission.has_been_rejected:
                continue

            try:
                url = Url.objects.all().get(url=urlsubmission.url)
            except Url.DoesNotExist:
                # if it already exists, then add the url to the organization.
                url = Url(url=urlsubmission.url)
                url.save()

            # organization might also be added... that not really a problem.
            try:
                url.organization.add(urlsubmission.for_organization)
                url.save()
            except Exception as e:
                log.error(e)

            urlsubmission.url_in_system = url
            urlsubmission.has_been_accepted = True
            urlsubmission.save()

        self.message_user(request, "Urls have been accepted and added to the system.")
    accept.short_description = "✅  Accept"
    actions.append('accept')

    def reject(self, request, queryset):
        for urlsubmission in queryset:
            urlsubmission.has_been_rejected = True
            urlsubmission.save()

        self.message_user(request, "Urls have been rejected.")
    reject.short_description = "❌  Reject"
    actions.append('reject')


class OrganizationSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('added_by_team', 'organization_name', 'has_been_accepted', 'added_on')
    search_fields = ('added_by_team__name', 'organization_name', 'organization_type_name')

    list_filter = ('added_by_team__name', 'has_been_accepted', 'added_by_team__participating_in_contest__name')

    fields = ('added_by_team', 'organization_country', 'organization_type_name', 'organization_name',
              'organization_address', 'organization_address_geocoded', 'url_in_system', 'has_been_accepted',
              'added_on')


admin.site.register(Contest, ContestAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(UrlSubmission, UrlSubmissionAdmin)
admin.site.register(OrganizationSubmission, OrganizationSubmissionAdmin)
