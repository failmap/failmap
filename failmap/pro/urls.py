from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import path

from failmap.pro import views

# todo: https://wsvincent.com/django-user-authentication-tutorial-signup/
urlpatterns = [
    path('', views.home),
    path('portfolio/', views.portfolio),
    path('issues/', views.issues),
    path('account/', views.account),
    path('mail/', views.mail),
    path('rescan_request/<str:scan_type>/<int:scan_id>/', views.rescan_request),
    url(r'^login/$', auth_views.LoginView.as_view(template_name='pro/registration/login.html'), name='login'),

    path('data/portfolio/', views.portfolio_data),
]
