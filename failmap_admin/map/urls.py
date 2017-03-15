# urls for scanners, maybe in their own url files
from django.conf.urls import url
from failmap_admin.map.views import index


urlpatterns = [
    url(r'^$', index, name='failmap'),
]
