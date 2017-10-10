from datetime import datetime  # admin functions

import pytz  # admin functions
from django.contrib import admin
from jet.admin import CompactInline

from failmap_admin.map.determineratings import (OrganizationRating, UrlRating, rate_organization,
                                                rate_url)
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.scanner_dns import brute_known_subdomains, certificate_transparency
from failmap_admin.scanners.scanner_http import scan_url_list_standard_ports
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys

from .models import Coordinate, Organization, Url

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
    list_display = ('url', 'is_dead_reason', 'not_resolvable', 'created_on')
    search_field = ('url', 'is_dead', 'is_dead_reason', 'not_resolvable')
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

    actions = ['rate_url', 'dns_subdomains', 'dns_transparency', 'discover_http_endpoints',
               'scan_url', 'declare_dead', 'print_on_commandline']

    def declare_dead(self, request, queryset):

        for url in queryset:
            url.is_dead = True
            url.is_dead_reason = "Killed via admin interface"
            url.is_dead_since = datetime.now(pytz.utc)
            url.save()

        self.message_user(request, "URL(s) have been declared dead")

    def rate_url(self, request, queryset):

        for url in queryset:
            rate_url(url=url)

        self.message_user(request, "URL(s) have been rated")

    def scan_url(self, request, queryset):

        urls_to_scan = []
        for url in queryset:
            urls_to_scan.append(url.url)

        s = ScannerTlsQualys()
        s.scan(urls_to_scan)

        self.message_user(request, "URL(s) have been scanned on TLS")

    def discover_http_endpoints(self, request, queryset):
        urls_to_scan = [url for url in queryset]
        scan_url_list_standard_ports(urls_to_scan)

        self.message_user(request, "URL(s) have been scanned for HTTP")

    def dns_subdomains(self, request, queryset):
        for url in queryset:
            brute_known_subdomains(url)

        self.message_user(request, "URL(s) have been scanned on known subdomains.")

    def dns_transparency(self, request, queryset):
        for url in queryset:
            certificate_transparency(url)

        self.message_user(request, "URL(s) have been scanned on known subdomains.")

    def print_on_commandline(self, request, queryset):
        for url in queryset:
            print(url.url)

    dns_subdomains.short_description = "Scan DNS (known subdomains)"
    dns_transparency.short_description = "Scan DNS (certificate transparency)"
    discover_http_endpoints.short_description = "Discover HTTP(S) endpoints"
    scan_url.short_description = "Scan (tls qualys)"
    rate_url.short_description = "Rate"
    declare_dead.short_description = "Declare dead"  # can still scan it
    print_on_commandline.short_description = "(debug) Print on command line"


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_field = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
