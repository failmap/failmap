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
from django.conf.urls import include, url
from django.contrib import admin

# Django 1.10 http://stackoverflow.com/questions/38744285/
# django-urls-error-view-must-be-a-callable-or-a-list-tuple-in-the-case-of-includ#38744286

urlpatterns = [
    url(r'^jet/', include('jet.urls', 'jet')),  # Django JET URLS
    url(r'^jet/dashboard/', include('jet.dashboard.urls',
                                    'jet-dashboard')),  # Django JET dashboard URLS
    url(r'^admin/', admin.site.urls),
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/manual/', include('failmap_admin.scanners.urls')),
    url(r'^scanners/', include('failmap_admin.scanners.urls')),
    url(r'^', include('failmap_admin.map.urls')),
]
