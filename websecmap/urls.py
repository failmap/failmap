"""admin URL Configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

import sys

from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.template.response import TemplateResponse
from django.urls import path, re_path
from rest_framework import routers, serializers, viewsets
from django.conf.urls.static import static


# register Jet Dashboard views
import websecmap.app.dashboard_module_views  # noqa  # pylint: disable=unused-import

# Django 1.10 http://stackoverflow.com/questions/38744285/
# django-urls-error-view-must-be-a-callable-or-a-list-tuple-in-the-case-of-includ#38744286
from websecmap.organizations.models import Coordinate, Organization
from . import __version__

admin.site.site_header = f"Web Security Map Admin {__version__}"
# Don't show version in title, as that might be shared without auth
admin.site.site_title = "Web Security Map Admin"


def trigger_error():
    # See: https://docs.sentry.io/platforms/python/django/
    division_by_zero = 1 / 0  # noqa
    print(division_by_zero)


admin_urls = [
    path("sentry-debug/", trigger_error),
    # add static resources to the admin directory, so routing on the production servers hits the application.
    path("admin/jet/", include("jet.urls", "jet")),  # Django JET URLS
    path("admin/jet/dashboard/", include("jet.dashboard.urls", "jet-dashboard")),  # Django JET dashboard URLS
    re_path(r"^admin/", admin.site.urls),
    re_path(r"^admin/doc/", include("django.contrib.admindocs.urls")),
    re_path(r"^nested_admin/", include("nested_admin.urls")),
]
frontend_urls = [
    re_path(r"", include("websecmap.map.urls")),
    re_path(r"data/", include("websecmap.map.urls_data")),
    re_path(r"^api/", include("websecmap.api.urls")),
    # re_path(r"^game/", include("websecmap.game.urls")),
]
interactive_urls = [
    path("authentication/", include("django.contrib.auth.urls")),
    # not using helpdesk anymore, might in the future.
    # url(r'helpdesk/', include('helpdesk.urls')),
]

urlpatterns = frontend_urls.copy()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name"]


class CoordinateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coordinate
        fields = ["organization", "geojsontype", "area"]


# ViewSets define the view behavior.
class CoordinateViewSet(viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    queryset = Coordinate.objects.all().filter(geojsontype="Point", is_dead=False)
    serializer_class = CoordinateSerializer


class OrganizationViewSet(viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r"coordinate", CoordinateViewSet)
router.register(r"organization", OrganizationViewSet)

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    # this should be above other admin urls
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# enable admin url's if this is an administrative (more secured/read-write) instance
if settings.ADMIN:
    urlpatterns += admin_urls

    # While rest framework is already secured with "IsAdminUser", not exposing anything
    # to normal users is better security, as it increases the attack surface (hugely).
    urlpatterns += [
        path("data/api/", include(router.urls)),
        path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    ]

# enable urls with interactive components that require database write access (login, url/org submit)
if settings.ADMIN or settings.INTERACTIVE:
    urlpatterns += interactive_urls

# debugging
# urlpatterns += [url(r'^silk/', include('silk.urls', namespace='silk'))]

# Nested inlines don't work with Django Jet (yet).
# urlpatterns += [url(r'^_nested_admin/', include('nested_admin.urls'))]

# set a different page for 500 errors to include sentry event ID.
# https://docs.sentry.io/clients/python/integrations/django/#message-references


def handler500(request):
    """500 error handler which includes ``request`` in the context.

    Templates: `500.html`
    Context: None
    """

    context = {
        "request": request,
        "admin_instance": settings.ADMIN,
    }

    # on privileged instance show the actual error message to hopefully be useful for the user
    if settings.ADMIN:
        _, value, _ = sys.exc_info()
        context["exception_message"] = value

    template_name = "500.html"  # You need to create a 500.html template.
    return TemplateResponse(request, template_name, context, status=500)


if settings.DEBUG:
    urlpatterns = [
        # test urls for error pages (cause normally we don't have them, ahum)
        re_path(r"^500/$", handler500),
    ] + urlpatterns
