from django.conf.urls import url
from django.contrib.auth import views as auth_views
from django.urls import path

from websecmap.pro import views

# todo: https://wsvincent.com/django-user-authentication-tutorial-signup/
urlpatterns = [
    path('', views.home),
    url(r'^login/$', auth_views.LoginView.as_view(template_name='pro/registration/login.html'), name='login'),

    path('account/', views.account),
    path('signup/', views.signup),
    path('mail/', views.mail),

    path('portfolio/', views.portfolio),
    path('data/portfolio/', views.portfolio_data),

    path('issues/', views.issues),
    path('issues/<str:list_name>/', views.issues),
    path('data/issues/', views.issue_data),
    path('rescan_request/<str:scan_type>/<int:scan_id>/', views.rescan_request),

    # path('data/explain/get_scan_data/<str:scan_type>/<int:scan_id>/')
]
