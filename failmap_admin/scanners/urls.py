# urls for scanners, maybe in their own url files
from django.conf.urls import include, url

from failmap_admin.scanners.views import UrlAutocomplete, index

urlpatterns = [
    url(r'^$', index, name='Run Manual Scans'),
    url(
        r'^url-autocomplete/$',
        UrlAutocomplete.as_view(),
        name='url-autocomplete',
    ),
]
