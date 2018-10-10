from django.contrib import admin
# overwrites for period tasks, allowing import and export buttons to work.
from django_celery_beat.admin import PeriodicTaskAdmin
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
from import_export.admin import ImportExportModelAdmin

from .models import Job


class JobAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'result_id', 'status', 'created_by', 'created_on', 'finished_on')
    list_filter = ('status', 'created_by')
    readonly_fields = ('name', 'task', 'result_id', 'result', 'status', 'created_on', 'finished_on')


admin.site.register(Job, JobAdmin)


class IEPeriodicTaskAdmin(PeriodicTaskAdmin, ImportExportModelAdmin):
    pass


class IESolarSchedule(ImportExportModelAdmin):
    pass


class IECrontabSchedule(ImportExportModelAdmin):
    pass


class IEIntervalSchedule(ImportExportModelAdmin):
    pass


admin.site.unregister(PeriodicTask)
admin.site.unregister(SolarSchedule)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(IntervalSchedule)
admin.site.register(PeriodicTask, IEPeriodicTaskAdmin)
admin.site.register(SolarSchedule, IESolarSchedule)
admin.site.register(CrontabSchedule, IESolarSchedule)
admin.site.register(IntervalSchedule, IEIntervalSchedule)
