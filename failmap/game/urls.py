from django.urls import path

from failmap.game import views

urlpatterns = [
    path('', views.scores),
    path('scores/', views.scores),
    path('team/', views.teams),
    path('submit_url/', views.submit_url),
    path('submit_organization/', views.submit_organisation),
    path('autocomplete/organization-autocomplete/', views.OrganizationAutocomplete.as_view()),
    path('autocomplete/organization-type-autocomplete/', views.OrganizationTypeAutocomplete.as_view()),
]
