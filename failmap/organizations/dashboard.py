from django.utils.translation import ugettext_lazy as _
from jet.dashboard import modules
from jet.dashboard.dashboard import Dashboard

from failmap.organizations import dashboard_modules


class CustomIndexDashboard(Dashboard):
    columns = 2

    def init_with_context(self, context):
        self.available_children.append(modules.LinkList)
        self.available_children.append(modules.RecentActions)
        self.available_children.append(modules.Feed)
        self.available_children.append(modules.AppList)

        self.children.append(modules.RecentActions(
            _('Recent Actions'),
            40,
            column=0,
            order=1
        ))

        self.children.append(dashboard_modules.RebuildRatings(
            _('Rebuild Ratings'),
            column=1,
            order=1
        ))

        self.children.append(modules.LinkList(
            _('Failmap resources'),
            children=[
                {
                    'title': _('Gitlab Repository'),
                    'url': 'https://gitlab.com/failmap/',
                    'external': True,
                },
                {
                    'title': _('Admin repository'),
                    'url': 'https://gitlab.com/failmap/failmap',
                    'external': True,
                },
                {
                    'title': _('Failmap Website'),
                    'url': 'https://faalkaart.nl',
                    'external': True,
                },
            ],
            column=1,
            order=2
        ), )
