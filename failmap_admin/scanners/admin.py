from django.contrib import admin
from .models import Endpoint, TlsQualysScan, TlsQualysScratchpad


class TlsQualysScanAdminInline(admin.StackedInline):
    model = TlsQualysScan
    extra = 0
    show_change_link = True

# can't make this admin, there is no join.
# class TlsQualysScratchpadAdminInline(admin.StackedInline):
#    model = TlsQualysScratchpad
#    extra = 0


class EndpointAdmin(admin.ModelAdmin):
    list_display = ('domain', 'server_name', 'ip', 'port', 'protocol', 'is_dead')
    search_fields = ('domain', 'server_name', 'ip', 'port', 'protocol', 'is_dead',
                     'is_dead_since', 'is_dead_reason')
    list_filter = ('domain', 'server_name', 'ip', 'port', 'protocol', 'is_dead')
    fieldsets = (
        (None, {
            'fields': ('domain', 'server_name', 'ip', 'port')
        }),
        ('dead endpoint management', {
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )
    inlines = [TlsQualysScanAdminInline]
    save_as = True  # Save as new is nice for duplicating endpoints.


class TlsQualysScanAdmin(admin.ModelAdmin):
    list_display = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'pending',
                    'pending_since', 'scan_date', 'rating_determined_on')
    search_fields = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'pending',
                     'pending_since', 'scan_date', 'rating_determined_on')
    list_filter = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust', 'pending',
                   'pending_since', 'scan_date', 'rating_determined_on')
    fields = ('endpoint', 'qualys_rating', 'qualys_rating_no_trust',
              'rating_determined_on', 'pending', 'pending_since')

    readonly_fields = ('scan_date', 'scan_time', 'scan_moment')


class TlsQualysScratchpadAdmin(admin.ModelAdmin):
    list_display = ('domain', 'when')
    search_fields = ('domain', 'when')
    list_filter = ('domain', 'when')
    fields = ('domain', 'data')
    readonly_fields = ['when']


admin.site.register(TlsQualysScan, TlsQualysScanAdmin)
admin.site.register(TlsQualysScratchpad, TlsQualysScratchpadAdmin)
admin.site.register(Endpoint, EndpointAdmin)
