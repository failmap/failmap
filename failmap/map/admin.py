from celery import group
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from ..app.models import Job
from ..celery import PRIO_HIGH
from .geojson import import_from_scratch, update_coordinates
from .models import AdministrativeRegion, OrganizationRating, UrlRating


class OrganizationRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_organization(self, obj):
        return format_html(
            '<a href="../../organizations/organization/{id}/change">inspect organization</a>',
            id=format(obj.organization_id))

    list_display = ('organization', 'high', 'medium', 'low', 'when', 'inspect_organization')
    search_fields = (['organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('organization', 'organization__country', 'organization__type__name', 'rating', 'when')
    fields = ('organization', 'rating', 'high', 'medium', 'low', 'when', 'calculation')

    ordering = ["-when"]

    save_as = True


class UrlRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'high', 'medium', 'low', 'when', 'inspect_url')
    search_fields = (['url__organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('url', 'rating', 'when')
    fields = ('url', 'rating', 'high', 'medium', 'low', 'when', 'calculation')

    ordering = ["-when"]

    save_as = True


# todo: set is_imported flag after importing
class AdministrativeRegionAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('country', 'organization_type', 'admin_level', 'imported')
    search_fields = (['country', 'organization_type', 'admin_level'])
    list_filter = ('country', 'organization_type', 'admin_level', 'imported')
    fields = ('country', 'organization_type', 'admin_level', 'imported')

    actions = []

    def import_region(self, request, queryset):
        tasks = []

        for region in queryset:
            tasks.append(import_from_scratch.s([region.country], [region.organization_type]))

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


admin.site.register(AdministrativeRegion, AdministrativeRegionAdmin)
admin.site.register(OrganizationRating, OrganizationRatingAdmin)
admin.site.register(UrlRating, UrlRatingAdmin)
