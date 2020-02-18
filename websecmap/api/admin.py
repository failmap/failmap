import logging

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from websecmap.api import models

log = logging.getLogger(__package__)


@admin.register(models.SIDNUpload)
class SIDNUpload(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('by_user', 'at_when', 'state', 'amount_of_newly_added_domains')
    search_fields = (['by_user', 'at_when', 'state', 'amount_of_newly_added_domains'])
    list_filter = ['by_user', 'at_when', 'state', 'amount_of_newly_added_domains'][::-1]
    fields = ('by_user', 'at_when', 'state', 'amount_of_newly_added_domains', 'newly_added_domains', 'posted_data')

    readonly_fields = ['posted_data', 'newly_added_domains', 'amount_of_newly_added_domains']

    actions = []
