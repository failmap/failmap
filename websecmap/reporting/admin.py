from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

import websecmap.map.models
from websecmap.reporting import models


@admin.register(websecmap.map.models.OrganizationReport)
class OrganizationRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_organization(self, obj):
        return format_html(
            '<a href="../../organizations/organization/{id}/change">inspect organization</a>',
            id=format(obj.organization_id))

    list_display = ('organization', 'high', 'medium', 'low', 'ok', 'total_urls', 'ok_urls',
                    'total_endpoints', 'ok_endpoints', 'report', 'explained_high', 'explained_medium',
                    'explained_low', 'when', 'inspect_organization')
    search_fields = (['organization__name', 'when'])
    list_filter = ['organization', 'organization__country', 'organization__type__name', 'when'][::-1]
    # fields = [field.name for field in OrganizationRating._meta.get_fields() if field.name != "id"][::-1]

    fields = ('organization', 'total_urls', 'total_endpoints',
              'high',
              'medium',
              'low',
              'ok',
              'high_urls',
              'medium_urls',
              'low_urls',
              'ok_urls',
              'high_endpoints',
              'medium_endpoints',
              'low_endpoints',
              'ok_endpoints',
              'total_url_issues',
              'url_issues_high',
              'url_issues_medium',
              'url_issues_low',
              'url_ok',
              'total_endpoint_issues',
              'endpoint_issues_high',
              'endpoint_issues_medium',
              'endpoint_issues_low',
              'endpoint_ok',
              'explained_high',
              'explained_medium',
              'explained_low',
              'explained_high_urls',
              'explained_medium_urls',
              'explained_low_urls',
              'explained_high_endpoints',
              'explained_medium_endpoints',
              'explained_low_endpoints',
              'explained_total_url_issues',
              'explained_url_issues_high',
              'explained_url_issues_medium',
              'explained_url_issues_low',
              'explained_total_endpoint_issues',
              'explained_endpoint_issues_high',
              'explained_endpoint_issues_medium',
              'explained_endpoint_issues_low',
              'when',
              'calculation')

    def report(self, obj):
        return obj

    ordering = ["-when"]

    save_as = True


@admin.register(models.UrlReport)
class UrlRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'high', 'medium', 'low', 'ok', 'total_endpoints', 'ok_endpoints', 'when', 'inspect_url')
    search_fields = (['url__organization__name', 'url__url', 'when'])
    list_filter = ['url', 'when', 'url__organization__type', 'url__organization__country'][::-1]
    fields = ('url', 'total_endpoints',
              'total_issues',

              'high',
              'medium',
              'low',
              'ok',
              'high_endpoints',
              'medium_endpoints',
              'low_endpoints',
              'ok_endpoints',
              'total_url_issues',
              'url_issues_high',
              'url_issues_medium',
              'url_issues_low',
              'url_ok',
              'total_endpoint_issues',
              'endpoint_issues_high',
              'endpoint_issues_medium',
              'endpoint_issues_low',
              'endpoint_ok',
              'explained_high',
              'explained_medium',
              'explained_low',
              'explained_high_endpoints',
              'explained_medium_endpoints',
              'explained_low_endpoints',
              'explained_total_url_issues',
              'explained_url_issues_high',
              'explained_url_issues_medium',
              'explained_url_issues_low',
              'explained_total_endpoint_issues',
              'explained_endpoint_issues_high',
              'explained_endpoint_issues_medium',
              'explained_endpoint_issues_low',

              'when', 'calculation')

    ordering = ["-when"]

    save_as = True
