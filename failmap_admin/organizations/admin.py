from datetime import datetime  # admin functions

import pytz  # admin functions
from django.contrib import admin
from jet.admin import CompactInline

from failmap_admin.map.determineratings import DetermineRatings, OrganizationRating, UrlRating
from failmap_admin.scanners.models import Endpoint
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

    inlines = [UrlAdminInline, CoordinateAdminInline, OrganizationRatingAdminInline]

    actions = ['rate_organization', 'scan_organization']

    def rate_organization(self, request, queryset):

        for organization in queryset:
            dr = DetermineRatings()
            dr.rate_organization(organization=organization)

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
    list_display = ('organization', 'url', 'is_dead_reason', 'not_resolvable', 'created_on')
    search_field = ('url', 'is_dead', 'is_dead_reason', 'not_resolvable')
    list_filter = ('organization', 'url', 'is_dead', 'is_dead_since', 'is_dead_reason',
                   'not_resolvable')

    fieldsets = (
        (None, {
            'fields': ('url', 'organization')
        }),
        ('Resolvability', {
            'fields': ('not_resolvable', 'not_resolvable_since', 'not_resolvable_reason'),
        }),
        ('dead URL management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )

    def is_dead(self):
        if self.something == '1':
            return True
        return False

    is_dead.boolean = True
    is_dead = property(is_dead)

    inlines = [EndpointAdminInline, UrlRatingAdminInline]

    actions = ['rate_url', 'scan_url', 'declare_dead', 'print_on_commandline']

    def declare_dead(self, request, queryset):

        for url in queryset:
            url.is_dead = True
            url.is_dead_reason = "Killed via admin interface"
            url.is_dead_since = datetime.now(pytz.utc)
            url.save()

        self.message_user(request, "URL(s) have been declared dead")

    def rate_url(self, request, queryset):

        for url in queryset:
            dr = DetermineRatings()
            dr.rate_url(url=url)

        self.message_user(request, "URL(s) have been rated")

    def scan_url(self, request, queryset):

        urls_to_scan = []
        for url in queryset:
            urls_to_scan.append(url.url)

        s = ScannerTlsQualys()
        s.scan(urls_to_scan)

        self.message_user(request, "URL(s) have been scanned")

    def print_on_commandline(self, request, queryset):
        for url in queryset:
            print(url.url)

    rate_url.short_description = "Rate"
    scan_url.short_description = "Scan"
    declare_dead.short_description = "Declare dead"  # can still scan it


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_field = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
