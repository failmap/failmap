# urls for scanners, maybe in their own url files
import proxy.views
from constance import config
from django.urls import path, re_path
from django.views.i18n import JavaScriptCatalog

from websecmap.map import views

# todo: organization type converter doesn't work yet... using slug as an alternative.

static_urlpatterns = [
    path("", views.index),
    path("empty", views.emptypage),
    path("security.txt", views.security_txt, name="security_txt"),
    path(".well-known/security.txt", views.security_txt, name="well_known_security_txt"),
    path("robots.txt", views.robots_txt),
    path("manifest.json", views.manifest_json),
    # Unused:
    # path(
    #     "autocomplete/<c:country>/<slug:organization_type>
    #     /organization/<str:parameter>", views.organization_autcomplete
    # ),
    path("images/screenshot/<int:endpoint_id>/", views.screenshot),
    # Proxy maptile requests,
    # In production this can be done by caching proxy, this makes sure it works for dev. as well.
    re_path(
        r"^proxy/(?P<url>https://api.mapbox.com/styles/v1/mapbox/.*./$)",
        proxy.views.proxy_view,
        {"requests_args": {"params": {"access_token": config.MAPBOX_ACCESS_TOKEN}}},
    ),
    # translations for javascript files. Copied from the manual.
    # https://docs.djangoproject.com/en/2.0/topics/i18n/translation/
    # cache_page(86400, key_prefix='js18n')
    re_path(r"^jsi18n/map/$", JavaScriptCatalog.as_view(packages=["websecmap.map"]), name="javascript-catalog"),
]

urlpatterns = static_urlpatterns
