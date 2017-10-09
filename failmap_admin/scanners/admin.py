from django.contrib import admin
from jet.admin import CompactInline

from failmap_admin.map.determineratings import OrganizationRating, UrlRating, rate_url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys

from .models import (Endpoint, EndpointGenericScan, Screenshot, State, TlsQualysScan,
                     TlsQualysScratchpad, Url, EndpointGenericScanScratchpad)


class TlsQualysScanAdminInline(CompactInline):
    model = TlsQualysScan
    extra = 0
    show_change_link = True
    ordering = ["-rating_determined_on"]

# can't make this admin, there is no join. And there shouldn't be.
# class TlsQualysScratchpadAdminInline(admin.StackedInline):
#    model = TlsQualysScratchpad
#    extra = 0


class EndpointAdmin(admin.ModelAdmin):
    list_display = ('url', 'domain', 'discovered_on', 'ip', 'port', 'protocol', 'is_dead_since',
                    'tls_scan_count')
    search_fields = ('url__url', 'domain', 'server_name', 'ip', 'port', 'protocol', 'is_dead',
                     'is_dead_since', 'is_dead_reason')
    list_filter = ('server_name', 'ip', 'port', 'protocol', 'is_dead')
    fieldsets = (
        (None, {
            'fields': ('url', 'domain', 'server_name', 'ip', 'port', 'discovered_on')
        }),
        ('dead endpoint management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )

    readonly_fields = ['discovered_on']

    def tls_scan_count(self, inst):
        return TlsQualysScan.objects.filter(endpoint=inst.id).count()

    inlines = [TlsQualysScanAdminInline]
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

        s = ScannerTlsQualys()
        s.scan(urls_to_scan)

        self.message_user(request, "URL(s) have been scanned")

    rate_url.short_description = "Rate (url)"
    scan_url.short_description = "Scan (url)"


class TlsQualysScanAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'qualys_message',
                    'scan_moment', 'rating_determined_on')
    search_fields = ('endpoint__url__url', 'qualys_rating', 'qualys_rating_no_trust',
                     'scan_date', 'rating_determined_on')
    list_filter = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
                   'scan_date', 'rating_determined_on', 'qualys_message')
    fields = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
              'rating_determined_on')

    readonly_fields = ('scan_date', 'scan_time', 'scan_moment')

    actions = ['rate_url', 'scan_url']

    def rate_url(self, request, queryset):

        for tlsqualysscan in queryset:
            rate_url(url=tlsqualysscan.endpoint.url)

        self.message_user(request, "URL(s) have been rated")

    def scan_url(self, request, queryset):

        urls_to_scan = []
        for tlsqualysscan in queryset:
            urls_to_scan.append(tlsqualysscan.endpoint.url.url)

        s = ScannerTlsQualys()
        s.scan(urls_to_scan)

        self.message_user(request, "URL(s) have been scanned")

    rate_url.short_description = "Rate (url)"
    scan_url.short_description = "Scan (url)"


class TlsQualysScratchpadAdmin(admin.ModelAdmin):
    list_display = ('domain', 'when')
    search_fields = ('domain', 'when')
    list_filter = ('domain', 'when')
    fields = ('domain', 'data')
    readonly_fields = ['when']


class ScreenshotAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'domain', 'created_on', 'filename')
    search_fields = ('endpoint__url__url', 'domain', 'created_on', 'filename')
    list_filter = ('endpoint', 'domain', 'created_on', 'filename')
    fields = ('endpoint', 'domain', 'created_on', 'filename', 'width_pixels', 'height_pixels')
    readonly_fields = ['created_on']


class StateAdmin(admin.ModelAdmin):
    list_display = ('scanner', 'value', 'since')
    search_fields = ('scanner', 'value', 'since')
    list_filter = ('scanner', 'value', 'since')
    fields = ('scanner', 'value', 'since')
    readonly_fields = ['since']


class EndpointGenericScanAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'type', 'domain', 'rating',
                    'explanation', 'last_scan_moment', 'rating_determined_on')
    search_fields = ('endpoint__url__url', 'type', 'domain', 'rating',
                     'explanation', 'last_scan_moment', 'rating_determined_on')
    list_filter = ('endpoint', 'type', 'domain', 'rating',
                   'explanation', 'last_scan_moment', 'rating_determined_on')
    fields = ('endpoint', 'type', 'domain', 'rating',
              'explanation', 'last_scan_moment', 'rating_determined_on')

class EndpointGenericScanScratchpadAdmin(admin.ModelAdmin):
    list_display = ('type', 'domain', 'when', 'data')
    search_fields = ('type', 'domain', 'when', 'data')
    list_filter = ('type', 'domain', 'when', 'data')
    fields = ('type', 'domain', 'when', 'data')


admin.site.register(TlsQualysScan, TlsQualysScanAdmin)
admin.site.register(TlsQualysScratchpad, TlsQualysScratchpadAdmin)
admin.site.register(Endpoint, EndpointAdmin)
admin.site.register(Screenshot, ScreenshotAdmin)
admin.site.register(State, StateAdmin)
admin.site.register(EndpointGenericScan, EndpointGenericScanAdmin)
admin.site.register(EndpointGenericScanScratchpad, EndpointGenericScanScratchpadAdmin)
