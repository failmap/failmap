from django.utils.translation import ugettext_lazy as _
from jet.dashboard import modules
from failmap_admin.organizations import dashboard_modules
from jet.dashboard.dashboard import Dashboard, AppIndexDashboard


# todo: add history to dashboard.
class CustomIndexDashboard(Dashboard):
    columns = 2

    def init_with_context(self, context):
        self.available_children.append(modules.LinkList)
        self.available_children.append(modules.RecentActions)
        self.available_children.append(modules.Feed)
        self.available_children.append(modules.AppList)
        self.available_children.append(dashboard_modules.SmartAddUrl)

        self.children.append(modules.RecentActions(
            _('Recent Actions'),
            10,
            column=0,
            order=1
        ))

        self.children.append(dashboard_modules.SmartAddUrl(
            _('Smart Add Url\'s'),
            column=1,
            order=1
        ))

        self.children.append(modules.LinkList(
            _('Failmap resources'),
            children=[
                {
                    'title': _('Github Repository'),
                    'url': 'https://github.com/failmap/',
                    'external': True,
                },
                {
                    'title': _('Admin repository'),
                    'url': 'https://github.com/failmap/admin',
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
