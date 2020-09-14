from django.contrib.auth import views as auth_views
from django.urls import path
from django.urls import re_path

from websecmap.pro import views
from websecmap.pro.view import explain

# todo: https://wsvincent.com/django-user-authentication-tutorial-signup/
urlpatterns = [
    path("", views.home),
    re_path(r"^login/$", auth_views.LoginView.as_view(template_name="pro/registration/login.html"), name="login"),
    path("account/", views.account),
    path("signup/", views.signup),
    path("mail/", views.mail),
    path("portfolio/", views.portfolio),
    path("data/portfolio/", views.portfolio_data),
    path("issues/", views.issues),
    path("issues/<str:list_name>/", views.issues),
    path("data/issues/", views.issue_data),
    path("rescan_request/<str:scan_type>/<int:scan_id>/", views.rescan_request),
    path("data/explain/get_canned_explanations/", explain.get_canned_explanations_view),
    path("data/explain/get_explain_costs/", explain.get_explain_costs_view),
    path("data/explain/get_scan_data/<int:scan_id>/<str:scan_type>/", explain.get_scan_data_view),
    path("data/explain/try_explain/<int:scan_id>/<str:scan_type>/<str:explanation>/", explain.try_explain_view),
    path("data/explain/extend_explanation/<int:scan_id>/<str:scan_type>/", explain.extend_explanation_view),
    path("data/explain/remove_explanation/<int:scan_id>/<str:scan_type>/", explain.remove_explanation_view),
]
