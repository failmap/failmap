from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from failmap.pro.models import Account, FailmapOrganizationDataFeed, UrlList, UrlListReport

# Register your models here.


@admin.register(Account)
class AccountAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'enable_logins', )
    search_fields = ('name', )
    list_filter = ['enable_logins'][::-1]
    fields = ('name', 'enable_logins',)


@admin.register(UrlList)
class UrlListAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'account', )
    search_fields = ('name', 'account__name')
    list_filter = ['account'][::-1]
    fields = ('name', 'account', 'urls')


@admin.register(FailmapOrganizationDataFeed)
class FailmapOrganizationDataFeedAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('organization',)
    search_fields = ('organization__name', )
    fields = ('organization', 'urllist')


@admin.register(UrlListReport)
class UrlListReportAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    def inspect_urllist(self, obj):
        return format_html(
            '<a href="../../pro/urllist/{id}/change">inspect urllist</a>',
            id=format(obj.urllist_id))

    def report(self, obj):
        return obj

    list_display = ('urllist', 'total_urls', 'total_endpoints', 'report', 'explained_high', 'explained_medium',
                    'explained_low', 'when', 'inspect_urllist')
    search_fields = (['organization__name', 'when'])
    list_filter = ['urllist', 'urllist__account', 'when'][::-1]
    fields = [field.name for field in UrlListReport._meta.get_fields() if field.name != "id"][::-1]
