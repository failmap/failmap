from adminsortable2.admin import SortableAdminMixin
from celery import group
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from ..app.models import Job
from ..celery import PRIO_HIGH, app
from .geojson import import_from_scratch, update_coordinates
from .models import (AdministrativeRegion, Configuration, OrganizationRating, UrlRating,
                     VulnerabilityStatistic)


@admin.register(OrganizationRating)
class OrganizationRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_organization(self, obj):
        return format_html(
            '<a href="../../organizations/organization/{id}/change">inspect organization</a>',
            id=format(obj.organization_id))

    list_display = ('organization', 'high', 'medium', 'low', 'when', 'inspect_organization')
    search_fields = (['organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('organization', 'organization__country', 'organization__type__name', 'rating', 'when')
    fields = ('organization', 'total_urls', 'total_endpoints',
              'high',
              'medium',
              'low',
              'high_urls',
              'medium_urls',
              'low_urls',
              'high_endpoints',
              'medium_endpoints',
              'low_endpoints',
              'total_url_issues',
              'url_issues_high',
              'url_issues_medium',
              'url_issues_low',
              'total_endpoint_issues',
              'endpoint_issues_high',
              'endpoint_issues_medium',
              'endpoint_issues_low',

              'explained_high',
              'explained_medium',
              'explained_low',
              'explained_high_urls',
              'explained_medium_urls',
              'explained_low_urls',
              'explained_high_endpoints',
              'explained_medium_endpoints',
              'explained_low_endpoints',
              'explained_total_url_issues',
              'explained_url_issues_high',
              'explained_url_issues_medium',
              'explained_url_issues_low',
              'explained_total_endpoint_issues',
              'explained_endpoint_issues_high',
              'explained_endpoint_issues_medium',
              'explained_endpoint_issues_low',

              'when',
              'calculation')

    ordering = ["-when"]

    save_as = True


@admin.register(UrlRating)
class UrlRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'high', 'medium', 'low', 'when', 'inspect_url')
    search_fields = (['url__organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('url', 'rating', 'when')
    fields = ('url', 'total_endpoints',
              'total_issues',

              'high',
              'medium',
              'low',
              'high_endpoints',
              'medium_endpoints',
              'low_endpoints',
              'total_url_issues',
              'url_issues_high',
              'url_issues_medium',
              'url_issues_low',
              'total_endpoint_issues',
              'endpoint_issues_high',
              'endpoint_issues_medium',
              'endpoint_issues_low',

              'explained_high',
              'explained_medium',
              'explained_low',
              'explained_high_endpoints',
              'explained_medium_endpoints',
              'explained_low_endpoints',
              'explained_total_url_issues',
              'explained_url_issues_high',
              'explained_url_issues_medium',
              'explained_url_issues_low',
              'explained_total_endpoint_issues',
              'explained_endpoint_issues_high',
              'explained_endpoint_issues_medium',
              'explained_endpoint_issues_low',

              'when', 'calculation')

    ordering = ["-when"]

    save_as = True


# todo: set is_imported flag after importing
@admin.register(AdministrativeRegion)
class AdministrativeRegionAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('country', 'organization_type', 'admin_level', 'imported')
    search_fields = (['country', 'organization_type', 'admin_level'])
    list_filter = ('country', 'organization_type', 'admin_level', 'imported')
    fields = ('country', 'organization_type', 'admin_level', 'imported')

    actions = []

    def import_region(self, request, queryset):
        tasks = []

        for region in queryset:
            tasks.append(import_from_scratch.s([region.country], [region.organization_type])
                         | add_configuration.si(region.country, region.organization_type))

        task_name = "%s (%s) " % ("Import region", ','.join(map(str, list(queryset))))
        task = group(tasks)

        job = Job.create(task, task_name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, 'Job created, <a href="%s">%s</a>' % (link, task_name))

    import_region.short_description = '🛃  Import region'
    actions.append(import_region)

    # ah, hmm... abstractions...
    # something something abstractions
    def update_coordinates(self, request, queryset):
        tasks = []

        for region in queryset:
            tasks.append(update_coordinates.s([region.country], [region.organization_type]))

        task_name = "%s (%s) " % ("Update region", ','.join(map(str, list(queryset))))
        task = group(tasks)

        job = Job.create(task, task_name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, 'Job created, <a href="%s">%s</a>' % (link, task_name))
    update_coordinates.short_description = '🛂  Update region'
    actions.append(update_coordinates)


@app.task(queue='storage')
def add_configuration(country, organization_type):
    a = Configuration(
        country=country,
        organization_type=organization_type,
        is_the_default_option=False,
        is_displayed=False,
        is_scanned=False
    )
    a.save()


@admin.register(Configuration)
class ConfigurationAdmin(SortableAdminMixin, ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('country', 'organization_type', 'is_displayed', 'is_the_default_option', 'is_scanned', )
    search_fields = (['country', 'organization_type', ])
    list_filter = ('country', 'organization_type', 'is_displayed', 'is_the_default_option', 'is_scanned',)
    fields = ('country', 'organization_type', 'is_displayed', 'is_the_default_option', 'is_scanned', )

    actions = []

    def display(self, request, queryset):

        for configuration in queryset:
            configuration.is_displayed = True
            configuration.save()

    display.short_description = '☀️ Display'
    actions.append(display)

    def hide(self, request, queryset):

        for configuration in queryset:
            configuration.is_displayed = False
            configuration.save()

    hide.short_description = '🌑 Hide'
    actions.append(hide)

    def allow_scanning(self, request, queryset):

        for configuration in queryset:
            configuration.is_scanned = True
            configuration.save()

    allow_scanning.short_description = '❤️  Allow scanning'
    actions.append(allow_scanning)

    def stop_scanning(self, request, queryset):

        for configuration in queryset:
            configuration.is_scanned = False
            configuration.save()

    stop_scanning.short_description = '💔  Stop scanning'
    actions.append(stop_scanning)

    def set_default(self, request, queryset):

        for configuration in queryset:
            configuration.is_the_default_option = True
            configuration.save()

    set_default.short_description = '😀  Set default'
    actions.append(set_default)

    def remove_default(self, request, queryset):

        for configuration in queryset:
            configuration.is_the_default_option = False
            configuration.save()

    remove_default.short_description = '😭  Remove default'
    actions.append(remove_default)


@admin.register(VulnerabilityStatistic)
class VulnerabilityStatisticAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('country', 'organization_type', 'scan_type', 'when', 'high', 'medium', 'low')
