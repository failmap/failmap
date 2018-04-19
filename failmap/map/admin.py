from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

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


class AdministrativeRegionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('country', 'organization_type', 'admin_level', 'imported')
    search_fields = (['country', 'organization_type', 'admin_level'])
    list_filter = ('country', 'organization_type', 'admin_level', 'imported')
    fields = ('country', 'organization_type', 'admin_level', 'imported')


admin.site.register(AdministrativeRegion, AdministrativeRegionAdmin)
admin.site.register(OrganizationRating, OrganizationRatingAdmin)
admin.site.register(UrlRating, UrlRatingAdmin)
