from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from websecmap.reporting import models


@admin.register(models.UrlReport)
class UrlRatingAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    # do NOT load the calculation field, as that will be slow.
    # https://stackoverflow.com/questions/34774028/how-to-ignore-loading-huge-fields-in-django-admin-list-display
    def get_queryset(self, request):
        qs = super(UrlRatingAdmin, self).get_queryset(request)

        # tell Django to not retrieve mpoly field from DB
        qs = qs.defer('calculation')
        return qs

    def inspect_url(self, obj):
        return format_html('<a href="../../organizations/url/{id}/change">inspect</a>',
                           id=format(obj.url_id))

    list_display = ('url', 'high', 'medium', 'low', 'ok', 'total_endpoints', 'ok_endpoints', 'at_when', 'inspect_url')
    search_fields = (['url__organization__name', 'url__url', 'at_when'])
    list_filter = ['url', 'at_when', 'url__organization__type', 'url__organization__country'][::-1]
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

              'at_when', 'calculation')

    ordering = ["-at_when"]

    save_as = True
