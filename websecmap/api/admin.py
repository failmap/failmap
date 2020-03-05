import logging

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from websecmap.api import models
from websecmap.api.logic import sidn_handle_domain_upload

log = logging.getLogger(__package__)


@admin.register(models.SIDNUpload)
class SIDNUpload(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ('by_user', 'at_when', 'state', 'amount_of_newly_added_domains')
    search_fields = (['by_user', 'at_when', 'state', 'amount_of_newly_added_domains'])
    list_filter = ['by_user', 'at_when', 'state', 'amount_of_newly_added_domains'][::-1]
    fields = ('by_user', 'at_when', 'state', 'amount_of_newly_added_domains', 'newly_added_domains', 'posted_data')

    actions = []

    def reprocess(self, request, queryset):
        for upload in queryset:
            sidn_handle_domain_upload.apply_async([upload.id])
        self.message_user(request, "Requeued tasks. Can take a while.")
    reprocess.short_description = "🔁  Reprocess (async)"
    actions.append('reprocess')
