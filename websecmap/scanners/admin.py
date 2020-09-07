from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline
from jet.filters import RelatedFieldAjaxListFilter

from websecmap.scanners import models
from websecmap.scanners.proxy import check_proxy
from websecmap.scanners.scanner.internet_nl_v2_websecmap import (progress_running_scan,
                                                                 recover_and_retry)


class EndpointGenericScanInline(CompactInline):
    model = models.EndpointGenericScan
    extra = 0
    show_change_link = True
    ordering = ["-rating_determined_on"]


@admin.register(models.UrlIp)
class UrlIpAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    search_fields = ('url__url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    list_filter = ['url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since'][::-1]
    fields = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused', 'is_unused_since', 'is_unused_reason')
    readonly_fields = ['discovered_on']


@admin.register(models.Endpoint)
class EndpointAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'url', 'visit', 'discovered_on', 'ip_version', 'port', 'protocol', 'is_dead', 'is_dead_since',
                    'is_dead_reason')
    search_fields = ('url__url', 'ip_version', 'port', 'protocol', 'is_dead',
                     'is_dead_since', 'is_dead_reason')
    list_filter = ['url__organization__country', 'url__organization__type__name',
                   'ip_version', 'port', 'protocol', 'is_dead', 'is_dead_reason', 'discovered_on'][::-1]
    fieldsets = (
        (None, {
            'fields': ('url', 'ip_version', 'protocol', 'port', 'discovered_on')
        }),
        ('dead endpoint management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )

    readonly_fields = ['discovered_on']

    @staticmethod
    def visit(inst):
        if not inst:
            return "- no url, how?"
        url = "%s://%s:%s/" % (inst.protocol, inst.url.url, inst.port)
        return format_html("<a href='%s' target='_blank'>Visit</a>" % url)

    inlines = [EndpointGenericScanInline]
    save_as = True  # Save as new is nice for duplicating endpoints.


@admin.register(models.TlsQualysScratchpad)
class TlsQualysScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('domain', 'at_when')
    search_fields = ('domain', 'at_when')
    list_filter = ['domain', 'at_when'][::-1]
    fields = ('domain', 'data')
    readonly_fields = ['at_when']


@admin.register(models.Screenshot)
class ScreenshotAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'created_on', 'filename')
    search_fields = ('endpoint__url__url', 'created_on', 'filename')
    list_filter = ['endpoint', 'created_on', 'filename'][::-1]
    fields = ('endpoint', 'image', 'created_on', 'filename', 'width_pixels', 'height_pixels')
    readonly_fields = ['created_on', 'image']


@admin.register(models.EndpointGenericScan)
class EndpointGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    def get_queryset(self, request):
        qs = super(EndpointGenericScanAdmin, self).get_queryset(request)

        # Because the endpoint, to display, needs url data, it will try to retrieve that for every
        # record. Here we already include those results, so the page loads 10x faster (at okay speeds now)
        qs = qs.prefetch_related('endpoint', 'endpoint__url')

        return qs

    list_display = ('endpoint', 'type', 'rating',
                    'last_scan_moment', 'rating_determined_on',
                    'comply_or_explain_is_explained', 'explain', 'is_the_latest_scan')
    search_fields = ('endpoint__url__url', 'type', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')

    list_filter = ['endpoint__url__organization__country', 'endpoint__url__organization__type__name',
                   'endpoint__url__is_dead',
                   ('endpoint', RelatedFieldAjaxListFilter), 'type', 'rating',
                   'explanation', 'last_scan_moment', 'rating_determined_on',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead',
                   'comply_or_explain_is_explained', 'comply_or_explain_explained_on',
                   'comply_or_explain_case_handled_by', 'comply_or_explain_explanation_valid_until',
                   'is_the_latest_scan'
                   ][::-1]

    fieldsets = (
        (None, {
            'fields': ('endpoint', 'type', 'rating', 'explanation',
                       'evidence', 'last_scan_moment', 'rating_determined_on', 'is_the_latest_scan')
        }),
        ('comply or explain', {
            'fields': ('comply_or_explain_is_explained', 'comply_or_explain_explanation_valid_until',
                       'comply_or_explain_explanation', 'comply_or_explain_explained_by',
                       'comply_or_explain_explained_on', 'comply_or_explain_case_handled_by',
                       'comply_or_explain_case_additional_notes'),
        }),
    )

    def explain(self, object):
        return format_html("<a href='./{}/change/#/tab/module_1/'>Explain</a>", object.pk)

    readonly_fields = ['last_scan_moment', 'rating_determined_on']


@admin.register(models.UrlGenericScan)
class UrlGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'type', 'rating',
                    'explanation', 'last_scan_moment', 'rating_determined_on',
                    'comply_or_explain_is_explained', 'explain', 'is_the_latest_scan', 'short_evidence')
    search_fields = ('url__url', 'type', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')
    list_filter = ['url__organization__country', 'url__organization__type__name', 'type', 'rating',
                   'explanation', 'last_scan_moment', 'rating_determined_on',
                   'comply_or_explain_is_explained', 'comply_or_explain_explained_on',
                   'comply_or_explain_case_handled_by', 'comply_or_explain_explanation_valid_until',
                   'is_the_latest_scan'
                   ][::-1]

    @staticmethod
    def short_evidence(obj):
        return obj.evidence[0:60]

    fieldsets = (
        (None, {
            'fields': ('url', 'type', 'rating', 'explanation', 'evidence', 'last_scan_moment', 'rating_determined_on',
                       'is_the_latest_scan')
        }),
        ('comply or explain', {
            'fields': ('comply_or_explain_is_explained', 'comply_or_explain_explanation_valid_until',
                       'comply_or_explain_explanation', 'comply_or_explain_explained_by',
                       'comply_or_explain_explained_on', 'comply_or_explain_case_handled_by',
                       'comply_or_explain_case_additional_notes'),
        }),
    )

    def explain(self, object):
        return format_html("<a href='./{}/change/#/tab/module_1/'>Explain</a>", object.pk)

    readonly_fields = ['last_scan_moment', 'rating_determined_on']


@admin.register(models.EndpointGenericScanScratchpad)
class EndpointGenericScanScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('type', 'domain', 'at_when', 'data')
    search_fields = ('type', 'domain', 'at_when', 'data')
    list_filter = ['type', 'domain', 'at_when', 'data'][::-1]
    fields = ('type', 'domain', 'at_when', 'data')


@admin.register(models.InternetNLV2Scan)
class InternetNLV2ScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'type', 'scan_id', 'online', 'state', 'state_message', 'last_state_check',
                    'last_state_change', 'domains')
    search_fields = ('subject_urls__url', 'scan_id')
    list_filter = ('state', 'state_message', 'last_state_check', 'last_state_change', 'type')
    fields = ('type', 'scan_id', 'state', 'state_message', 'last_state_check', 'last_state_change', 'metadata',
              'retrieved_scan_report', 'subject_urls')
    # todo: subject_urls inline

    readonly_fields = ['subject_urls', 'metadata', 'retrieved_scan_report']

    @staticmethod
    def domains(obj):
        return obj.subject_urls.count()

    @staticmethod
    def online(obj):
        from constance import config
        return mark_safe(f"<a href='{config.INTERNET_NL_API_USERNAME}:{config.INTERNET_NL_API_PASSWORD}"
                         f"@{config.INTERNET_NL_API_URL}/requests/{obj.scan_id}' target='_blank'>online</a>")

    actions = []

    def attempt_rollback(self, request, queryset):
        for scan in queryset:
            recover_and_retry.apply_async([scan])
        self.message_user(request, "Rolling back asynchronously. May take a while.")
    attempt_rollback.short_description = "Attempt rollback (async)"
    actions.append('attempt_rollback')

    def progress_scan(self, request, queryset):
        for scan in queryset:
            tasks = progress_running_scan(scan)
            tasks.apply_async()
        self.message_user(request, "Attempting to progress scans (async).")
    progress_scan.short_description = "Progress scan (async)"
    actions.append('progress_scan')


@admin.register(models.InternetNLV2StateLog)
class InternetNLV2StateLogAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('pk', 'scan', 'state', 'state_message', 'last_state_check', 'at_when')
    search_fields = ('scan__scan_id', )
    list_filter = ('state', 'state_message', 'last_state_check', 'at_when')
    fields = ('scan', 'state', 'state_message', 'last_state_check', 'at_when')


@admin.register(models.ScanProxy)
class ScanProxyAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'protocol', 'address', 'check_result', 'check_result_date',
                    'currently_used_in_tls_qualys_scan', 'last_claim_at', 'manually_disabled', 'is_dead',
                    'request_speed_in_ms', 'qualys_capacity_current', 'qualys_capacity_max',
                    'qualys_capacity_this_client')
    search_fields = ('address', )
    list_filter = ('protocol',  'is_dead', 'is_dead_since', 'check_result',
                   'manually_disabled', 'qualys_capacity_current')
    fields = ('protocol', 'address', 'currently_used_in_tls_qualys_scan', 'is_dead', 'is_dead_since', 'is_dead_reason',
              'manually_disabled', 'check_result', 'check_result_date',
              'request_speed_in_ms', 'qualys_capacity_current', 'qualys_capacity_max', 'qualys_capacity_this_client',
              'last_claim_at')

    actions = []

    def check_qualys_proxy(self, request, queryset):
        for proxy in queryset:
            check_proxy.apply_async([proxy])
        self.message_user(request, "Proxing checked asynchronously. May take some time before results come in.")
    check_qualys_proxy.short_description = "Check proxy"
    actions.append('check_qualys_proxy')

    def release_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.out_of_resource_counter = 0
            proxy.currently_used_in_tls_qualys_scan = False
            proxy.save()

        self.message_user(request, "Proxies released.")
    release_proxy.short_description = "Release proxy"
    actions.append('release_proxy')

    def reset_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.is_dead = False
            proxy.out_of_resource_counter = 0
            proxy.currently_used_in_tls_qualys_scan = False
            proxy.save()

        self.message_user(request, "Proxies reset.")
    reset_proxy.short_description = "Reset proxy"
    actions.append('reset_proxy')

    def disable_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.manually_disabled = True
            proxy.save()

        self.message_user(request, "Proxies disabled.")
    disable_proxy.short_description = "Disable proxy"
    actions.append('disable_proxy')

    def enable_proxy(self, request, queryset):
        for proxy in queryset:
            proxy.manually_disabled = False
            proxy.save()

        self.message_user(request, "Proxies enabled.")
    enable_proxy.short_description = "Enable proxy"
    actions.append('enable_proxy')


@admin.register(models.PlannedScan)
class PlannedScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'activity', 'scanner', 'state', 'last_state_change_at', 'requested_at_when',
                    'finished_at_when')
    search_fields = ('url__url', 'activity', 'scanner', 'state')
    list_filter = ['activity', 'scanner', 'state', 'last_state_change_at', 'requested_at_when',
                   'finished_at_when'][::-1]
    fields = ('url', 'activity', 'scanner', 'state', 'last_state_change_at', 'requested_at_when', 'finished_at_when')


@admin.register(models.PlannedScanStatistic)
class PlannedScanStatisticAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('at_when', 'data')
    list_filter = ['at_when'][::-1]
    fields = ('at_when', 'data')
