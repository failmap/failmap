from django.contrib import admin
from jet.admin import CompactInline

from .models import Coordinate, Organization, Url
# Solved: http://stackoverflow.com/questions/11754877/
#   troubleshooting-related-field-has-invalid-lookup-icontains
#   while correct, error should point to ModelAdmin.search fields documentation


class UrlAdminInline(CompactInline):
    model = Url
    extra = 0
    show_change_link = True


class CoordinateAdminInline(admin.StackedInline):
    model = Coordinate
    extra = 0


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'country')
    search_fields = (['name', 'country', 'type__name'])
    list_filter = ('name', 'type__name', 'country')  # todo: type is now listed as name, confusing
    fields = ('name', 'type', 'country')

    inlines = [UrlAdminInline, CoordinateAdminInline]


class UrlAdmin(admin.ModelAdmin):
    list_display = ('organization', 'url', 'isdeadreason')
    search_field = ('url', 'isdead', 'isdeadreason')
    list_filter = ('url', 'isdead', 'isdeadsince', 'isdeadreason')

    fieldsets = (
        (None, {
            'fields': ('url', 'organization')
        }),
        ('dead URL management', {
            'fields': ('isdead', 'isdeadsince', 'isdeadreason'),
        }),
    )

    def isdead(self):
        if self.something == '1':
            return True
        return False

    isdead.boolean = True
    isdead = property(isdead)


class CoordinateAdmin(admin.ModelAdmin):
    list_display = ('organization', 'geojsontype')
    search_field = ('organization', 'geojsontype')
    list_filter = ('organization', 'geojsontype')
    fields = ('organization', 'geojsontype', 'area')


admin.site.register(Organization, OrganizationAdmin)
admin.site.register(Url, UrlAdmin)
admin.site.register(Coordinate, CoordinateAdmin)
