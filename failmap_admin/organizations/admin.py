from django.contrib import admin
from jet.admin import CompactInline

from failmap_admin.map.determineratings import DetermineRatings, OrganizationRating, UrlRating
from failmap_admin.scanners.models import Endpoint

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
    fields = ('name', 'type', 'country')

    inlines = [UrlAdminInline, CoordinateAdminInline, OrganizationRatingAdminInline]

    actions = ['rate_organization']

    def rate_organization(self, request, queryset):

        for organization in queryset:
            dr = DetermineRatings()
            dr.rate_organization(organization=organization)

        self.message_user(request, "Organization(s) have been rated")

    rate_organization.short_description = \
        "Rate selected Organizations based on available scansresults"


class UrlAdmin(admin.ModelAdmin):
    list_display = ('organization', 'url', 'is_dead_reason')
    search_field = ('url', 'is_dead', 'is_dead_reason')
    list_filter = ('organization', 'url', 'is_dead', 'is_dead_since', 'is_dead_reason')

    fieldsets = (
        (None, {
            'fields': ('url', 'organization')
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

    actions = ['rate_url']

    def rate_url(self, request, queryset):

        for url in queryset:
            dr = DetermineRatings()
            dr.rate_url(url=url)

        self.message_user(request, "URL(s) have been rated")

    rate_url.short_description = "Rate selected URLs based on available scansresults"


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_field = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
