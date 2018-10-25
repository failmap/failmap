from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
# overwrites for period tasks, allowing import and export buttons to work.
from django_celery_beat.admin import PeriodicTaskAdmin
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Job, Volunteer


class JobAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', 'result_id', 'status', 'created_by', 'created_on', 'finished_on')
    list_filter = ('status', 'created_by')
    readonly_fields = ('name', 'task', 'result_id', 'result', 'status', 'created_on', 'finished_on')


admin.site.register(Job, JobAdmin)


class IEPeriodicTaskAdmin(PeriodicTaskAdmin, ImportExportModelAdmin):
    list_display = ('name', 'enabled', 'interval', 'queue', 'task', 'args')

    save_as = True

    class Meta:
        ordering = ["-name"]


class IEUser(ImportExportModelAdmin):
    pass


class IEGroup(ImportExportModelAdmin):
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


class VolunteerInline(admin.StackedInline):
    model = Volunteer
    can_delete = False
    verbose_name_plural = 'Volunteer information'


# Thank you:
# https://stackoverflow.com/questions/47941038/how-should-i-add-django-import-export-on-the-user-model?rq=1
class UserResource(resources.ModelResource):
    class Meta:
        model = User
        # fields = ('first_name', 'last_name', 'email')


class GroupResource(resources.ModelResource):
    class Meta:
        model = Group


class UserAdmin(BaseUserAdmin, ImportExportModelAdmin):
    resource_class = UserResource
    inlines = (VolunteerInline, )

    list_display = ('username', 'organization', 'first_name', 'last_name', 'email', 'is_staff')

    @staticmethod
    def organization(obj):
        return obj.volunteer.organization


# I don't know if the permissions between two systems have the same numbers... Only one way to find out :)
class GroupAdmin(BaseGroupAdmin, ImportExportModelAdmin):
    resource_class = GroupResource


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)
