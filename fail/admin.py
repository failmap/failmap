from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import Coordinate, Organization, Url


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('type', 'country', 'name')
    search_fields = ('type', 'country', 'name')
    list_filter = ( 'type', 'country')
    fields = ('name', 'type', 'country')


class UrlAdmin(admin.ModelAdmin):
    list_display = ('organization', 'url', 'isdeadreason')
    search_field = ('url', 'isdead', 'isdeadreason')
    list_filter = ('url', 'isdead', 'isdeadsince', 'isdeadreason')
    fields = ('url', 'organization', 'isdead', 'isdeadsince', 'isdeadreason')


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
