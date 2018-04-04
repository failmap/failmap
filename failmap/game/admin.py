from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline

from failmap.game.forms import TeamForm
from failmap.game.models import Contest, Submission, Team


class TeamInline(CompactInline):
    model = Team
    extra = 0
    can_delete = False
    ordering = ["name"]


class SubmissionInline(CompactInline):
    model = Submission
    extra = 0
    can_delete = False
    ordering = ["url"]


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

    form = TeamForm


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

    inlines = [SubmissionInline]


class SubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('added_by_team', 'has_been_accepted', 'url', 'organization_name', 'added_on')
    search_fields = ('url', 'added_by_team__name', 'organization_name', 'organization_type_name')

    list_filter = ('added_by_team__name', 'has_been_accepted', 'added_by_team__participating_in_contest__name')

    fields = ('added_by_team', 'organization_country', 'organization_type_name', 'organization_name',
              'organization_address', 'organization_address_geocoded', 'url', 'url_in_system', 'has_been_accepted',
              'added_on')


admin.site.register(Contest, ContestAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(Submission, SubmissionAdmin)
