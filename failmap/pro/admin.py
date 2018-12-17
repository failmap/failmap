from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from failmap.pro.models import Account, FailmapOrganizationDataFeed, UrlList

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
