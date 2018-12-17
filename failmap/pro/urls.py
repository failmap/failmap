from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import path

from failmap.pro import views

# todo: https://wsvincent.com/django-user-authentication-tutorial-signup/
urlpatterns = [
    path('', views.home),
    path('urls/', views.urls),
    path('scans/', views.scans),
    path('mail/', views.mail),
    url(r'^login/$', auth_views.LoginView.as_view(template_name='pro/registration/login.html'), name='login'),
]
