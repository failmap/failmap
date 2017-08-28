# urls for scanners, maybe in their own url files
from django.conf.urls import include, url

from failmap_admin.scanners.views import UrlAutocomplete, tls

urlpatterns = [

    # autocomplete feature for the tls scan form.
    url(
        r'^url-autocomplete/$',
        UrlAutocomplete.as_view(),
        name='url-autocomplete',
    ),
    url(r'^scanners/tls/', tls),
    url(r'^tls/$', tls)
]
