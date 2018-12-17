from django.urls import path

from failmap.pro import views

urlpatterns = [
    path('', views.dummy)
]
