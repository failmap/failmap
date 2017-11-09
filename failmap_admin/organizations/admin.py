from datetime import datetime  # admin functions

import pytz  # admin functions
from django.contrib import admin
from jet.admin import CompactInline

from failmap_admin.map.determineratings import (OrganizationRating, UrlRating, rate_organization,
                                                rate_urls)
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_dns import brute_known_subdomains, certificate_transparency
from failmap_admin.scanners.scanner_http import scan_urls_on_standard_ports
from failmap_admin.scanners.scanner_plain_http import scan_urls as plain_http_scan_urls
from failmap_admin.scanners.scanner_screenshot import screenshot_urls
from failmap_admin.scanners.scanner_security_headers import scan_urls as security_headers_scan_urls
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys

from .models import Coordinate, Organization, OrganizationType, Url

# Solved: http://stackoverflow.com/questions/11754877/
#   troubleshooting-related-field-has-invalid-lookup-icontains
#   while correct, error should point to ModelAdmin.search fields documentation


class UrlAdminInline(CompactInline):
    model = Url
    extra = 0
    show_change_link = True


class EndpointAdminInline(CompactInline):
    model = Endpoint
    extra = 0
    show_change_link = True
    ordering = ["is_dead"]


class CoordinateAdminInline(CompactInline):
    model = Coordinate
    extra = 0


class OrganizationRatingAdminInline(CompactInline):
    model = OrganizationRating
    extra = 0
    ordering = ["-when"]


class UrlRatingAdminInline(CompactInline):
    model = UrlRating
    extra = 0
    ordering = ["-when"]


class OrganizationAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/action_buttons.js', )

    list_display = ('name', 'type', 'country')
    search_fields = (['name', 'country', 'type__name'])
    list_filter = ('name', 'type__name', 'country')  # todo: type is now listed as name, confusing
    fields = ('name', 'type', 'country', 'twitter_handle')

    inlines = [UrlAdminInline, CoordinateAdminInline, OrganizationRatingAdminInline]  #

    actions = ['rate_organization', 'scan_organization']

    def rate_organization(self, request, queryset):

        for organization in queryset:
            rate_organization(organization=organization)

        self.message_user(request, "Organization(s) have been rated")

    def scan_organization(self, request, queryset):

        # it's best to add all url's in one go, resulting in the fastest processing

        urls_to_scan = []

        for organization in queryset:
            urls = Url.objects.filter(organization=organization)
            for url in urls:
                urls_to_scan.append(url.url)

        s = ScannerTlsQualys()
        s.scan(urls_to_scan)

        self.message_user(request, "Organization(s) have been scanned")

    rate_organization.short_description = \
        "Rate selected Organizations based on available scansresults"

    scan_organization.short_description = \
        "Scan selected Organizations"


class UrlAdmin(admin.ModelAdmin):
    class Media:
        js = ('js/action_buttons.js', )

    list_display = ('url', 'is_dead_reason', 'not_resolvable', 'created_on')
    search_fields = ('url', )
    list_filter = ('url', 'is_dead', 'is_dead_since', 'is_dead_reason',
                   'not_resolvable', 'uses_dns_wildcard', 'organization')

    fieldsets = (
        (None, {
            'fields': ('url', 'organization', 'created_on')
        }),
        ('DNS', {
            'fields': ('uses_dns_wildcard', ),
        }),
        ('Resolvability', {
            'fields': ('not_resolvable', 'not_resolvable_since', 'not_resolvable_reason'),
        }),
        ('dead URL management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )
    readonly_fields = ['created_on']

    def is_dead(self):
        if self.something == '1':
            return True
        return False

    is_dead.boolean = True
    is_dead = property(is_dead)

    inlines = [EndpointAdminInline, UrlRatingAdminInline]

    actions = []

    def dns_certificate_transparency(self, request, queryset):
        certificate_transparency([url for url in queryset])
        self.message_user(request, "URL(s) have been scanned on known subdomains: Done")
    actions.append('dns_certificate_transparency')
    dns_certificate_transparency.short_description = "Discover subdomains (using certificate transparency)"

    def dns_known_subdomains(self, request, queryset):
        brute_known_subdomains([url for url in queryset])
        self.message_user(request, "Discover subdomains (using known subdomains): Done")
    dns_known_subdomains.short_description = "Discover subdomains (using known subdomains)"
    actions.append('dns_known_subdomains')

    def discover_http_endpoints(self, request, queryset):
        scan_urls_on_standard_ports([url for url in queryset])
        self.message_user(request, "Discover http(s) endpoints: Done")
    discover_http_endpoints.short_description = "Discover http(s) endpoints"
    actions.append('discover_http_endpoints')

    def scan_tls_qualys(self, request, queryset):
        ScannerTlsQualys().scan([url.url for url in queryset])
        self.message_user(request, "Scan TLS (qualys, slow): Scheduled with Priority")
    scan_tls_qualys.short_description = "Scan TLS (qualys, slow)"
    actions.append('scan_tls_qualys')

    def security_headers(self, request, queryset):
        security_headers_scan_urls(urls=([url for url in queryset]))
        self.message_user(request, "Scan Security Headers: done")
    security_headers.short_description = "Scan Security Headers"
    actions.append('security_headers')

    def plain_http_scan(self, request, queryset):
        plain_http_scan_urls([url for url in queryset])
        self.message_user(request, "Scan Plain Http: done")
    plain_http_scan.short_description = "Scan Plain Http"
    actions.append('plain_http_scan')

    def screenshots(self, request, queryset):
        screenshot_urls([url for url in queryset])
        self.message_user(request, "Create screenshot: Done")
    screenshots.short_description = "Create screenshot"
    actions.append('screenshots')

    def rate_url(self, request, queryset):
        rate_urls([url for url in queryset])
        self.message_user(request, "Rate Url: done")
    rate_url.short_description = "Rate Url"
    actions.append('rate_url')

    def rate_organization_(self, request, queryset):
        rate_organization([url.organization for url in queryset])
        self.message_user(request, "Rate Organization: done")
    rate_organization_.short_description = "Rate Organization"
    actions.append('rate_organization_')

    def declare_dead(self, request, queryset):
        for url in queryset:
            url.is_dead = True
            url.is_dead_reason = "Killed via admin interface"
            url.is_dead_since = datetime.now(pytz.utc)
            url.save()
        self.message_user(request, "Declare dead: Done")
    declare_dead.short_description = "Declare dead"
    actions.append('declare_dead')


class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ('name', )
    search_fields = ('name', )
    list_filter = ('name', )
    fields = ('name', )


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_fields = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
admin.site.register(OrganizationType, OrganizationTypeAdmin)
