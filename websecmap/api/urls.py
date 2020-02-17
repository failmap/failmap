from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import path, register_converter

from websecmap import converters
from websecmap.api import views

register_converter(converters.OrganizationTypeConverter, 'ot')
register_converter(converters.WeeksConverter, 'w')
register_converter(converters.DaysConverter, 'd')
register_converter(converters.CountryConverter, 'c')
register_converter(converters.OrganizationIdConverter, 'oid')
register_converter(converters.JsonConverter, 'json')


urlpatterns = [
    url(r'^login/$', auth_views.LoginView.as_view(template_name='api/login.html'), name='login'),

    path('', views.show_sidn_upload_),
    path('SIDN/', views.show_sidn_upload_),
    path('SIDN/layers/', views.get_map_configuration_),
    path('SIDN/2nd_level_urls_on_map/<c:country>/<slug:organization_type>/', views.get_2ndlevel_domains_),
    path('SIDN/upload/', views.sidn_domain_upload_)
]
