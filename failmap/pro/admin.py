import random

from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from failmap.pro.models import (Account, CreditMutation, FailmapOrganizationDataFeed, RescanRequest,
                                SubdomainDataFeed, UrlList, UrlListReport)

# Register your models here.


@admin.register(Account)
class AccountAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('name', 'enable_logins', 'credits')
    search_fields = ('name', )
    list_filter = ['enable_logins'][::-1]
    fields = ('name', 'enable_logins', 'credits')

    readonly_fields = ['credits']

    actions = []

    def give_1000_credits(self, request, queryset):
        for account in queryset:
            account.receive_credits(1000, "Received 1000 credits via admin command.")
        self.message_user(request, 'Credits given')

    give_1000_credits.short_description = 'Give 1000 credits'
    actions.append(give_1000_credits)

    # todo: what if the amount of credits is negative?
    def spend_random_credits(self, request, queryset):
        message = ""
        for account in queryset:
            number = random.randint(1, 100)
            try:
                if account.can_spend(number):
                    account.spend_credits(number, "Spent %s credits via admin command." % number)
            except ValueError:
                message = "At least one account could not spend credits due to insufficient credits."
        self.message_user(request, 'Spend credits. %s' % message)
    spend_random_credits.short_description = 'Spend random credits (1 - 100)'
    actions.append(spend_random_credits)


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


@admin.register(SubdomainDataFeed)
class SubdomainDataFeedAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('subdomain',)
    search_fields = ('subdomain', )
    fields = ('subdomain', 'urllist')


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


@admin.register(CreditMutation)
class CreditMutationAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    all_fields = [field.name for field in CreditMutation._meta.get_fields() if field.name != "id"][::-1]
    search_fields = ['account']
    list_filter = ['account', 'when'][::-1]
    list_display = all_fields[::-1]
    fields = all_fields

    # You can't mutate this directly, it will give a lot of pain. If you made a mistake, compensate.
    readonly_fields = all_fields


@admin.register(RescanRequest)
class RescanRequestAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    all_fields = [field.name for field in RescanRequest._meta.get_fields() if field.name != "id"][::-1]
    search_fields = ['account']
    list_filter = ['account', 'added_on'][::-1]
    list_display = ['account', 'scan_type', 'added_on']
    fields = all_fields

    # You can't mutate this directly, it will give a lot of pain. If you made a mistake, compensate.
    # so many references, this will overload the admin.
    readonly_fields = all_fields
