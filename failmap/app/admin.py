from django.contrib import admin

from .models import Job


class JobAdmin(admin.ModelAdmin):
    list_display = ('name', 'result_id', 'status', 'created_by', 'created_on', 'finished_on')
    list_filter = ('status', 'created_by')
    readonly_fields = ('name', 'task', 'result_id', 'result', 'status', 'created_on', 'finished_on')


admin.site.register(Job, JobAdmin)
