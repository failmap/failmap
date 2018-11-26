from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline
from jet.filters import RelatedFieldAjaxListFilter

from failmap.scanners.models import (Endpoint, EndpointGenericScan, EndpointGenericScanScratchpad,
                                     InternetNLScan, Screenshot, TlsQualysScan, TlsQualysScratchpad,
                                     TlsScan, UrlGenericScan, UrlIp)


class TlsQualysScanAdminInline(CompactInline):
    model = TlsQualysScan
    extra = 0
    show_change_link = True
    ordering = ["-rating_determined_on"]


class EndpointGenericScanInline(CompactInline):
    model = EndpointGenericScan
    extra = 0
    show_change_link = True
    ordering = ["-rating_determined_on"]


# can't make this admin, there is no join. And there shouldn't be.
# class TlsQualysScratchpadAdminInline(admin.StackedInline):
#    model = TlsQualysScratchpad
#    extra = 0


@admin.register(UrlIp)
class UrlIpAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    search_fields = ('url__url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    list_filter = ['url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since'][::-1]
    fields = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused', 'is_unused_since', 'is_unused_reason')
    readonly_fields = ['discovered_on']


@admin.register(Endpoint)
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
    def tls_scans(inst):
        # slow subqueries are slow
        return 0
        return TlsQualysScan.objects.filter(endpoint=inst.id).count()

    @staticmethod
    def endpoint_generic_scans(inst):
        # slow subqueries are slow
        return 0
        return EndpointGenericScan.objects.filter(endpoint_id=inst.id).count()

    @staticmethod
    def url_generic_scans(inst):
        # slow subqueries are slow
        return 0
        return UrlGenericScan.objects.filter(url__endpoint=inst.id).count()

    @staticmethod
    def visit(inst):
        url = "%s://%s:%s/" % (inst.protocol, inst.url.url, inst.port)
        return format_html("<a href='%s' target='_blank'>Visit</a>" % url)

    inlines = [TlsQualysScanAdminInline, EndpointGenericScanInline]
    save_as = True  # Save as new is nice for duplicating endpoints.


@admin.register(TlsScan)
class TlsScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'rating', 'rating_no_trust', 'comply_or_explain_is_explained', 'compared_to_qualys',
                    'explanation', 'last_scan_moment', 'rating_determined_on', 'explain', 'is_the_latest_scan')
    search_fields = ('endpoint__url__url', 'rating', 'rating_no_trust',
                     'scan_date', 'rating_determined_on')

    list_filter = ['endpoint__url__organization__country', 'endpoint__url__organization__type__name',
                   'rating', 'rating_no_trust', 'explanation',
                   'scan_date', 'rating_determined_on',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead',
                   'comply_or_explain_is_explained', 'comply_or_explain_explained_on',
                   'comply_or_explain_case_handled_by', 'comply_or_explain_explanation_valid_until',
                   'is_the_latest_scan'
                   ][::-1]

    fieldsets = (
        (None, {
            'fields': ('endpoint', 'rating', 'rating_no_trust', 'explanation', 'evidence',
                       'rating_determined_on', 'last_scan_moment', 'is_the_latest_scan')
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

    @staticmethod
    def compared_to_qualys(instance):
        latest = TlsQualysScan.objects.all().filter(endpoint=instance.endpoint).latest('rating_determined_on')
        first = "💚" if latest.qualys_rating == instance.rating else "😞"
        second = "💚" if latest.qualys_rating_no_trust == instance.rating_no_trust else "😞"
        return "%s %s | %s %s" % (first, latest.qualys_rating, second, latest.qualys_rating_no_trust)

    readonly_fields = ('endpoint', 'rating', 'rating_no_trust', 'explanation', 'evidence',
                       'rating_determined_on', 'last_scan_moment', 'is_the_latest_scan')


@admin.register(TlsQualysScan)
class TlsQualysScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'qualys_message',
                    'last_scan_moment', 'rating_determined_on', 'comply_or_explain_is_explained', 'explain',
                    'is_the_latest_scan')
    search_fields = ('endpoint__url__url', 'qualys_rating', 'qualys_rating_no_trust',
                     'scan_date', 'rating_determined_on')

    # listing all endpoints takes ages
    list_filter = ['endpoint__url__organization__country', 'endpoint__url__organization__type__name',
                   'qualys_rating', 'qualys_rating_no_trust',
                   'scan_date', 'rating_determined_on', 'qualys_message',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead',
                   'comply_or_explain_is_explained', 'comply_or_explain_explained_on',
                   'comply_or_explain_case_handled_by', 'comply_or_explain_explanation_valid_until',
                   'is_the_latest_scan'
                   ][::-1]

    # loading related fields in django jet is not done in a smart way: everything is prefetched.
    # and when there are > 10000 objects of some sort, the system becomes insanely slow.
    # Should make it an autocomplete field... or something else.
    # therefore endpoint is set as a readonly_field.
    fieldsets = (
        (None, {
            'fields': ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
                       'rating_determined_on', 'last_scan_moment', 'is_the_latest_scan')
        }),
        ('comply or explain', {
            'fields': ('comply_or_explain_is_explained', 'comply_or_explain_explanation_valid_until',
                       'comply_or_explain_explanation', 'comply_or_explain_explained_by',
                       'comply_or_explain_explained_on', 'comply_or_explain_case_handled_by',
                       'comply_or_explain_case_additional_notes'),
        }),
    )

    readonly_fields = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
                       'rating_determined_on', 'last_scan_moment', 'is_the_latest_scan')

    def explain(self, object):
        return format_html("<a href='./{}/change/#/tab/module_1/'>Explain</a>", object.pk)


@admin.register(TlsQualysScratchpad)
class TlsQualysScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('domain', 'when')
    search_fields = ('domain', 'when')
    list_filter = ['domain', 'when'][::-1]
    fields = ('domain', 'data')
    readonly_fields = ['when']


@admin.register(Screenshot)
class ScreenshotAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'domain', 'created_on', 'filename')
    search_fields = ('endpoint__url__url', 'domain', 'created_on', 'filename')
    list_filter = ['endpoint', 'domain', 'created_on', 'filename'][::-1]
    fields = ('endpoint', 'domain', 'created_on', 'filename', 'width_pixels', 'height_pixels')
    readonly_fields = ['created_on']


@admin.register(EndpointGenericScan)
class EndpointGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'domain', 'type', 'rating',
                    'explanation', 'last_scan_moment', 'rating_determined_on',
                    'comply_or_explain_is_explained', 'explain', 'is_the_latest_scan')
    search_fields = ('endpoint__url__url', 'type', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')
    list_filter = ['endpoint__url__organization__country', 'endpoint__url__organization__type__name',
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

    readonly_fields = ['endpoint', 'type', 'rating', 'explanation', 'evidence', 'last_scan_moment',
                       'rating_determined_on', 'is_the_latest_scan']


@admin.register(UrlGenericScan)
class UrlGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'domain', 'type', 'rating',
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

    readonly_fields = ['url', 'type', 'rating', 'explanation', 'evidence', 'last_scan_moment', 'rating_determined_on',
                       'is_the_latest_scan']


@admin.register(EndpointGenericScanScratchpad)
class EndpointGenericScanScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('type', 'domain', 'when', 'data')
    search_fields = ('type', 'domain', 'when', 'data')
    list_filter = ['type', 'domain', 'when', 'data'][::-1]
    fields = ('type', 'domain', 'when', 'data')


@admin.register(InternetNLScan)
class InternetNLScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('started_on', 'finished_on', 'success', 'message')
    search_fields = ('message', 'status_url')
    list_filter = ('started_on', 'finished_on', 'success', 'message', )
    fields = ('started', 'started_on', 'finished', 'finished_on', 'success', 'message', 'status_url')
