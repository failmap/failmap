from django.contrib import admin
from django.utils.html import format_html

from .models import OrganizationRating, UrlRating


class OrganizationRatingAdmin(admin.ModelAdmin):
    def inspect_organization(self, obj):
        return format_html(
            '<a href="../../organizations/organization/{id}/change">inspect organization</a>',
            id=format(obj.organization_id))

    list_display = ('organization', 'rating', 'high', 'medium', 'low', 'when', 'inspect_organization')
    search_fields = (['organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('organization', 'rating', 'when')
    fields = ('organization', 'rating', 'high', 'medium', 'low', 'when', 'calculation')

    ordering = ["-when"]

    save_as = True


class UrlRatingAdmin(admin.ModelAdmin):
    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'rating', 'high', 'medium', 'low', 'when', 'inspect_url')
    search_fields = (['url__organization__name', 'rating', 'high', 'medium', 'low', 'when', 'calculation'])
    list_filter = ('url', 'rating', 'when')
    fields = ('url', 'rating', 'high', 'medium', 'low', 'when', 'calculation')

    ordering = ["-when"]

    save_as = True


admin.site.register(OrganizationRating, OrganizationRatingAdmin)
admin.site.register(UrlRating, UrlRatingAdmin)
