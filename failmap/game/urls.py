# urls for scanners, maybe in their own url files
from django.conf.urls import url

from failmap.game.views import (OrganizationAutocomplete, OrganizationTypeAutocomplete, scores,
                                submit_organisation, submit_url, teams)

urlpatterns = [

    url(r'^game/$', scores, name='scores'),
    url(r'^game/scores/$', scores, name='scores'),
    url(r'^game/team/$', teams, name='teams'),

    url(r'^game/submit_url/$', submit_url, name='submit url'),
    url(r'^game/submit_organisation/$', submit_organisation, name='submit url'),

    url(r'^game/autocomplete/organization-autocomplete/$', OrganizationAutocomplete.as_view(),
        name='organization-autocomplete'),

    url(r'^game/autocomplete/organization-type-autocomplete/$', OrganizationTypeAutocomplete.as_view(),
        name='organization-type-autocomplete'),
]
