import logging
from copy import deepcopy

from adminsortable2.admin import SortableAdminMixin
from celery import group
from django.contrib import admin
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from failmap.app.models import Job
from failmap.celery import PRIO_HIGH, app
from failmap.map import models
from failmap.map.geojson import import_from_scratch, update_coordinates
from failmap.map.report import compose_task

log = logging.getLogger(__package__)


@admin.register(models.OrganizationRating)
class OrganizationRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_organization(self, obj):
        return format_html(
            '<a href="../../organizations/organization/{id}/change">inspect organization</a>',
            id=format(obj.organization_id))

    list_display = ('organization', 'total_urls', 'total_endpoints', 'report', 'explained_high', 'explained_medium',
                    'explained_low', 'when', 'inspect_organization')
    search_fields = (['organization__name', 'when'])
    list_filter = ['organization', 'organization__country', 'organization__type__name', 'when'][::-1]
    # fields = [field.name for field in OrganizationRating._meta.get_fields() if field.name != "id"][::-1]

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

    def report(self, obj):
        return obj

    ordering = ["-when"]

    save_as = True


@admin.register(models.UrlRating)
class UrlRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'high', 'medium', 'low', 'total_endpoints', 'when', 'inspect_url')
    search_fields = (['url__organization__name', 'url__url', 'when'])
    list_filter = ['url', 'when', 'url__organization__type', 'url__organization__country'][::-1]
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


@admin.register(models.AdministrativeRegion)
class AdministrativeRegionAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('country', 'organization_type', 'admin_level', 'imported', 'import_message',
                    'resampling_resolution')
    search_fields = (['country', 'organization_type__name', 'admin_level'])
    list_filter = ['country', 'organization_type', 'admin_level', 'imported'][::-1]
    fields = ('country', 'organization_type', 'admin_level', 'imported', 'import_message', 'resampling_resolution')

    actions = []

    def import_region(self, request, queryset):
        tasks = []

        for region in queryset:
            organization_filter = {'country': region.country, 'type': region.organization_type}

            # you can't add tasks for reporting, as the data is not in the database to create the tasks yet.
            tasks.append(import_from_scratch.si([str(region.country)], [region.organization_type.name])
                         | add_configuration.si(region.country, region.organization_type)
                         | set_imported.si(region)
                         | report_country.si(organization_filter))

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
            tasks.append(update_coordinates.si([str(region.country)], [region.organization_type.name]))

        task_name = "%s (%s) " % ("Update region", ','.join(map(str, list(queryset))))
        task = group(tasks)

        job = Job.create(task, task_name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, 'Job created, <a href="%s">%s</a>' % (link, task_name))
    update_coordinates.short_description = '🛂  Update region'
    actions.append(update_coordinates)


@app.task(queue='storage')
def set_imported(region: models.AdministrativeRegion):
    region.imported = True
    region.save(update_fields=['imported'])


@app.task(queue='storage')
def report_country(organization_filter):
    tasks = compose_task(organizations_filter=organization_filter)
    tasks.apply_async()


@app.task(queue='storage')
def add_configuration(country, organization_type):

    if models.Configuration.objects.all().filter(country=country, organization_type=organization_type).exists():
        log.debug("This configuration already exists, skipping.")
        return

    # has earlier configuration of this country? Then add it after that country.
    tmp = models.Configuration.objects.all().filter(country=country).order_by('-display_order').first()
    if tmp:
        new_number = tmp.display_order + 1

        moveup = models.Configuration.objects.all().filter(display_order__gte=new_number).order_by('-display_order')
        for config in moveup:
            config.display_order += 1
            config.save()
    else:
        # otherwise add it to the end of the list.
        tmp = models.Configuration.objects.all().order_by('-display_order').first()

        if tmp:
            new_number = tmp.display_order + 1
        else:
            new_number = 1

    a = models.Configuration(
        country=country,
        organization_type=organization_type,
        is_the_default_option=False,
        is_displayed=False,
        is_scanned=False,
        is_reported=True,
        display_order=new_number
    )
    a.save()


@admin.register(models.Configuration)
# ImportExportModelAdmin and SortableAdminMixin don't work together.
# as sortableadmin contains a bug causing double ID's, we're prefering importexportmodeladmin. Makes ordering
# awful to handle. But we can manage by changing that to buttons that sort of work.
class ConfigurationAdmin(ImportExportModelAdmin, admin.ModelAdmin, SortableAdminMixin, ):

    list_display = ('display_order', 'country', 'organization_type', 'is_displayed', 'is_the_default_option',
                    'is_scanned', 'is_reported')
    search_fields = (['country', 'organization_type', ])
    list_filter = ['country', 'organization_type', 'is_displayed', 'is_the_default_option',
                   'is_scanned', 'is_reported'][::-1]
    fields = ('display_order',
              'country', 'organization_type', 'is_displayed', 'is_the_default_option', 'is_scanned', 'is_reported')

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

    def allow_reporting(self, request, queryset):

        for configuration in queryset:
            configuration.is_reported = True
            configuration.save()

    allow_reporting.short_description = '📄️  Allow Reporting'
    actions.append(allow_reporting)

    def stop_reporting(self, request, queryset):

        for configuration in queryset:
            configuration.is_reported = False
            configuration.save()

    stop_reporting.short_description = '📄  Stop Reporting'
    actions.append(stop_reporting)

    def create_report(self, request, queryset):

        for configuration in queryset:

            organization_filter = {'country': configuration.country, 'type': configuration.organization_type}

            log.debug(organization_filter)
            task = compose_task(organizations_filter=organization_filter)
            task.apply_async()

        self.message_user(request, 'Reports are being generated in the background.')

    create_report.short_description = '📄  Report'
    actions.append(create_report)

    def set_default(self, request, queryset):

        for configuration in queryset:

            models.Configuration.objects.all().update(is_the_default_option=False)

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

    def reorder(self, request, queryset):

        first_order = None

        for configuration in queryset:

            # set the first order, and keep counting from that.
            if not first_order:
                if not int(configuration.display_order):
                    first_order = 0
                    configuration.display_order = 0
                else:
                    first_order = configuration.display_order
            else:
                # second and more
                first_order += 1
                configuration.display_order = first_order

            configuration.save()

    reorder.short_description = 'Reorder'
    actions.append(reorder)

    @transaction.atomic
    def move_up(self, request, queryset):

        for configuration in queryset:
            next_config = models.Configuration.objects.all().order_by(
                '-display_order').filter(display_order__lt=configuration.display_order).first()
            if not next_config:
                log.debug("No next one")
                continue

            log.debug("Moving up: %s to %s" % (configuration.display_order, next_config.display_order))
            tmp = deepcopy(next_config.display_order)
            next_config.display_order = configuration.display_order
            configuration.display_order = tmp

            next_config.save(update_fields=['display_order'])
            configuration.save(update_fields=['display_order'])

    move_up.short_description = 'Move Up'
    actions.append(move_up)

    @transaction.atomic
    def move_down(self, request, queryset):

        for configuration in reversed(queryset):
            previous_config = models.Configuration.objects.all().order_by(
                'display_order').filter(display_order__gt=configuration.display_order).first()
            if not previous_config:
                log.debug("No previous one")
                continue

            log.debug("Moving down: %s to %s" % (configuration.display_order, previous_config.display_order))
            tmp = deepcopy(previous_config.display_order)
            previous_config.display_order = configuration.display_order
            configuration.display_order = tmp

            previous_config.save(update_fields=['display_order'])
            configuration.save(update_fields=['display_order'])

    move_down.short_description = 'Move Down'
    actions.append(move_down)


@admin.register(models.VulnerabilityStatistic)
class VulnerabilityStatisticAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('country', 'organization_type', 'scan_type', 'when', 'high', 'medium', 'low', 'urls', 'endpoints')
    list_filter = ['country', 'organization_type', 'scan_type', 'when', 'high', 'medium', 'low'][::-1]
    search_fields = (['country', 'organization_type', 'scan_type'])


@admin.register(models.MapDataCache)
class MapDataCacheAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('pk', 'country', 'organization_type', 'filters', 'when')
    list_filter = ['country', 'organization_type', 'filters', 'when'][::-1]
    search_fields = (['country', 'organization_type', 'filters'])

    readonly_fields = ['cached_on']

    @staticmethod
    def length(obj):
        # retrieving this causes a massive slowdown on getting the dataset
        return len(str(obj.dataset))
