# http://jet.readthedocs.io/en/latest/dashboard_custom_module.html
# needs: http://jet.readthedocs.io/en/latest/dashboard_custom_module.html#inherit-dashboard-module
# https://github.com/john-kurkowski/tldextract
# https://www.dabapps.com/blog/higher-level-query-api-django-orm/
# https://docs.djangoproject.com/en/1.10/intro/overview/#enjoy-the-free-api
# https://docs.djangoproject.com/en/1.10/topics/db/queries/
from datetime import datetime

import pytz
from django.contrib import messages
from django.shortcuts import redirect
from jet.dashboard.modules import DashboardModule


class RebuildRatings(DashboardModule):
    title = 'Rebuild Ratings'
    title_url = 'Rebuild Ratings'

    template = 'organizations/templates/RebuildRatings.html'


def rebuild_ratings(request):
    from failmap.map.rating import rebuild_ratings_async
    rebuild_ratings_async()

    messages.success(request, 'A new task that rebuilds ratings has been added (%s).' % datetime.now(pytz.utc))
    return redirect("/admin/map/")
