from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline
from jet.filters import RelatedFieldAjaxListFilter

from failmap.map.rating import rate_url

from .models import (Endpoint, EndpointGenericScan, EndpointGenericScanScratchpad, Screenshot,
                     TlsQualysScan, TlsQualysScratchpad, TlsScan, UrlGenericScan, UrlIp)


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


class UrlIpAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    search_fields = ('url__url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    list_filter = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused_since')
    fields = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused', 'is_unused_since', 'is_unused_reason')
    readonly_fields = ['discovered_on']


class EndpointAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'url', 'visit', 'discovered_on', 'ip_version', 'port', 'protocol', 'is_dead', 'is_dead_since',
                    'is_dead_reason')
    search_fields = ('url__url', 'ip_version', 'port', 'protocol', 'is_dead',
                     'is_dead_since', 'is_dead_reason')
    list_filter = ('ip_version', 'port', 'protocol', 'is_dead', 'is_dead_reason', 'discovered_on')
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

    actions = ['rate_url', 'scan_url']

    def rate_url(self, request, queryset):

        for endpoint in queryset:
            rate_url(url=endpoint.url)

        self.message_user(request, "URL(s) have been rated")

    def scan_url(self, request, queryset):

        urls_to_scan = []
        for endpoint in queryset:
            urls_to_scan.append(endpoint.url.url)

        # scan(urls_to_scan)
        raise NotImplementedError('WIP deprecated TODO')

        self.message_user(request, "URL(s) have been scanned")

    rate_url.short_description = "Rate (url)"
    scan_url.short_description = "Scan (url)"


class TlsScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'rating', 'rating_no_trust', 'compared_to_qualys', 'explanation',
                    'last_scan_moment', 'rating_determined_on')
    search_fields = ('endpoint__url__url', 'rating', 'rating_no_trust',
                     'scan_date', 'rating_determined_on')

    list_filter = ('rating', 'rating_no_trust', 'explanation',
                   'scan_date', 'rating_determined_on',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead'
                   )
    fields = ('endpoint', 'rating', 'rating_no_trust', 'explanation', 'evidence',
              'rating_determined_on', 'last_scan_moment')

    @staticmethod
    def compared_to_qualys(instance):
        latest = TlsQualysScan.objects.all().filter(endpoint=instance.endpoint).latest('rating_determined_on')
        first = "💚" if latest.qualys_rating == instance.rating else "😞"
        second = "💚" if latest.qualys_rating_no_trust == instance.rating_no_trust else "😞"
        return "%s %s | %s %s" % (first, latest.qualys_rating, second, latest.qualys_rating_no_trust)

    readonly_fields = ('scan_date', 'scan_time', 'last_scan_moment', 'endpoint')


class TlsQualysScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'qualys_message',
                    'last_scan_moment', 'rating_determined_on')
    search_fields = ('endpoint__url__url', 'qualys_rating', 'qualys_rating_no_trust',
                     'scan_date', 'rating_determined_on')

    # listing all endpoints takes ages
    list_filter = ('qualys_rating', 'qualys_rating_no_trust',
                   'scan_date', 'rating_determined_on', 'qualys_message',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead'
                   )

    # loading related fields in django jet is not done in a smart way: everything is prefetched.
    # and when there are > 10000 objects of some sort, the system becomes insanely slow.
    # Should make it an autocomplete field... or something else.
    # therefore endpoint is set as a readonly_field.
    fields = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
              'rating_determined_on', 'last_scan_moment')

    readonly_fields = ('scan_date', 'scan_time', 'last_scan_moment', 'endpoint')

    actions = ['rate_url', 'scan_url']

    def rate_url(self, request, queryset):

        for tlsqualysscan in queryset:
            rate_url(url=tlsqualysscan.endpoint.url)

        self.message_user(request, "URL(s) have been rated")

    # def scan_url(self, request, queryset):
    #
    #     urls_to_scan = []
    #     for tlsqualysscan in queryset:
    #         urls_to_scan.append(tlsqualysscan.endpoint.url.url)
    #
    #     scan(urls_to_scan)
    #
    #     self.message_user(request, "URL(s) have been scanned")

    rate_url.short_description = "Rate (url)"
    # scan_url.short_description = "Scan (url)"


class TlsQualysScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('domain', 'when')
    search_fields = ('domain', 'when')
    list_filter = ('domain', 'when')
    fields = ('domain', 'data')
    readonly_fields = ['when']


class ScreenshotAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'domain', 'created_on', 'filename')
    search_fields = ('endpoint__url__url', 'domain', 'created_on', 'filename')
    list_filter = ('endpoint', 'domain', 'created_on', 'filename')
    fields = ('endpoint', 'domain', 'created_on', 'filename', 'width_pixels', 'height_pixels')
    readonly_fields = ['created_on']


class EndpointGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('endpoint', 'domain', 'type', 'rating',
                    'explanation', 'last_scan_moment', 'rating_determined_on')
    search_fields = ('endpoint__url__url', 'type', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')
    list_filter = (('endpoint', RelatedFieldAjaxListFilter), 'type', 'rating',
                   'explanation', 'last_scan_moment', 'rating_determined_on',
                   'endpoint__protocol',
                   'endpoint__port', 'endpoint__ip_version', 'endpoint__discovered_on', 'endpoint__is_dead',
                   'endpoint__url__organization__country', 'endpoint__url__organization__type__name',
                   )

    fields = ('endpoint', 'type', 'rating',
              'explanation', 'evidence', 'last_scan_moment', 'rating_determined_on')

    readonly_fields = ['last_scan_moment', 'endpoint']


class UrlGenericScanAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('url', 'domain', 'type', 'rating',
                    'explanation', 'last_scan_moment', 'rating_determined_on')
    search_fields = ('url__url', 'type', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')
    list_filter = ('url__organization__country', 'url__organization__type__name', 'type', 'rating',
                   'explanation', 'last_scan_moment', 'rating_determined_on')
    fields = ('url', 'type', 'rating',
              'explanation', 'evidence', 'last_scan_moment', 'rating_determined_on')

    readonly_fields = ['last_scan_moment', 'url']


class EndpointGenericScanScratchpadAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('type', 'domain', 'when', 'data')
    search_fields = ('type', 'domain', 'when', 'data')
    list_filter = ('type', 'domain', 'when', 'data')
    fields = ('type', 'domain', 'when', 'data')


admin.site.register(TlsQualysScan, TlsQualysScanAdmin)
admin.site.register(TlsScan, TlsScanAdmin)
admin.site.register(TlsQualysScratchpad, TlsQualysScratchpadAdmin)
admin.site.register(Endpoint, EndpointAdmin)
admin.site.register(Screenshot, ScreenshotAdmin)
admin.site.register(EndpointGenericScan, EndpointGenericScanAdmin)
admin.site.register(UrlGenericScan, UrlGenericScanAdmin)
admin.site.register(EndpointGenericScanScratchpad, EndpointGenericScanScratchpadAdmin)
admin.site.register(UrlIp, UrlIpAdmin)
