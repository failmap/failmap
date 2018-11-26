from django.utils.translation import ugettext_lazy as _
from jet.dashboard import modules
from jet.dashboard.dashboard import Dashboard
from jet.dashboard.models import UserDashboardModule

from failmap.app import dashboard_modules


class ResetUserWidgetConfiguration:
    """This makes sure the user widget configurion stored in database is updated when the Dashboard class changes."""

    # https://github.com/geex-arts/django-jet/issues/26#issuecomment-309881393

    def get_or_create_module_models(self, user):
        module_models = []

        i = 0

        for module in self.children:
            column = module.column if module.column is not None else i % self.columns
            order = module.order if module.order is not None else int(i / self.columns)

            obj, created = UserDashboardModule.objects.get_or_create(
                title=module.title,
                app_label=self.app_label,
                user=user.pk,
                module=module.fullname(),
                column=column,
                order=order,
                settings=module.dump_settings(),
                children=module.dump_children()
            )
            module_models.append(obj)
            i += 1

        return module_models

    def load_modules(self):
        module_models = self.get_or_create_module_models(self.context['request'].user)

        loaded_modules = []

        for module_model in module_models:
            module_cls = module_model.load_module()
            if module_cls is not None:
                module = module_cls(model=module_model, context=self.context)
                loaded_modules.append(module)

        self.modules = loaded_modules


class CustomIndexDashboard(ResetUserWidgetConfiguration, Dashboard):
    columns = 3

    def init_with_context(self, context):
        self.available_children.append(modules.LinkList)

        # append an app list module for "Applications"
        self.children.append(modules.AppList(
            _('Content'),
            exclude=('auth.*', 'django_celery_beat.*',),
            column=1,
            order=0
        ))

        # append an app list module for "Administration"
        self.children.append(modules.AppList(
            _('Administration'),
            models=('auth.*', 'django_celery_beat.*',),
            column=2,
            order=0
        ))

        # append a recent actions module
        self.children.append(modules.RecentActions(
            _('Recent Actions'),
            10,
            column=0,
            order=1
        ))

        self.children.append(dashboard_modules.TaskProcessing(
            _('Task Processing Status (WIP)'),
            column=0,
            order=0
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
            column=2,
            order=2
        ), )


class CustomAppIndexDashboard(ResetUserWidgetConfiguration, Dashboard):
    columns = 2

    def init_with_context(self, context):
        self.available_children.append(modules.RecentActions)
        self.children.append(modules.RecentActions(
            _('Recent Actions for %s' % context['app_label'].capitalize()),
            40,
            column=0,
            order=1,
            include_list=[context['app_label'] + '.*'],
        ))
