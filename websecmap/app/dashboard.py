import logging

from django.core.exceptions import MultipleObjectsReturned
from django.utils.translation import gettext_lazy as _
from jet.dashboard import modules
from jet.dashboard.dashboard import Dashboard
from jet.dashboard.models import UserDashboardModule

log = logging.getLogger(__name__)


class ResetUserWidgetConfiguration(Dashboard):
    """This makes sure the user widget configurion stored in database is updated when the Dashboard class changes."""

    # https://github.com/geex-arts/django-jet/issues/26#issuecomment-309881393

    def get_or_create_module_models(self, user):
        module_models = []

        i = 0

        for module in self.children:
            column = module.column if module.column is not None else i % self.columns
            order = module.order if module.order is not None else int(i / self.columns)

            try:
                obj, _ = UserDashboardModule.objects.get_or_create(
                    title=module.title,
                    app_label=self.app_label,
                    user=user,
                    module=module.fullname(),
                    column=column,
                    order=order,
                    settings=module.dump_settings(),
                    children=module.dump_children(),
                )
                module_models.append(obj)
                i += 1
            except MultipleObjectsReturned:
                log.warning("Dashboard misconfiguration detected. Modules might be duplicated or missing.")

        return module_models

    def load_modules(self):
        module_models = self.get_or_create_module_models(self.context["request"].user)

        loaded_modules = []

        for module_model in module_models:
            module_cls = module_model.load_module()
            if module_cls is not None:
                module = module_cls(model=module_model, context=self.context)
                loaded_modules.append(module)

        self.modules = loaded_modules


class CustomIndexDashboard(ResetUserWidgetConfiguration):
    columns = 3

    def init_with_context(self, context):
        self.available_children.append(modules.LinkList)

        # append an app list module for "Applications"
        self.children.append(
            modules.AppList(
                _("Content"),
                exclude=("auth.*", "django_celery_beat.*", "constance.*"),
                column=1,
                order=0,
            )
        )

        # append an app list module for "Administration"
        self.children.append(
            modules.AppList(
                _("Administration"),
                models=("auth.*", "django_celery_beat.*", "constance.*"),
                column=2,
                order=0,
            )
        )

        # append a recent actions module
        self.children.append(modules.RecentActions(_("Recent Actions"), 10, column=0, order=1))

        self.children.append(
            modules.LinkList(
                _("Failmap resources"),
                children=[
                    {
                        "title": _("Gitlab Repository"),
                        "url": "https://gitlab.com/internet-cleanup-foundation/web-security-map/",
                        "external": True,
                    },
                    {
                        "title": _("Monitoring"),
                        "url": "https://monitoring.internetcleanup.foundation",
                        "external": True,
                    },
                ],
                column=0,
                order=2,
            ),
        )

        self.children.append(
            modules.ModelList(
                _("Quicklinks"),
                models=(
                    "organizations.OrganizationType"
                    "organizations.Organization"
                    "organizations.Url"
                    "scanners.Endpoint"
                    "scanners.EndpointGenericScan"
                    "scanners.UrlGenericScan"
                    "scanners.Scanner"
                    "scanners.ScanType"
                ),
                column=0,
                order=3,
            )
        )


class CustomAppIndexDashboard(ResetUserWidgetConfiguration):
    columns = 2

    def init_with_context(self, context):
        self.available_children.append(modules.RecentActions)
        self.children.append(
            modules.RecentActions(
                _(f"Recent Actions for {context['app_label'].capitalize()}"),
                40,
                column=1,
                order=0,
                include_list=[context["app_label"] + ".*"],
            )
        )

        if context["app_label"] == "game":
            self.children.append(
                modules.LinkList(
                    _("Quick Actions"),
                    children=[
                        {
                            "title": _("Verify New Urls"),
                            "url": "/admin/game/urlsubmission/?"
                            "has_been_accepted__exact=0&has_been_rejected__exact=0&o=-6.2.3",
                            "external": False,
                        },
                    ],
                    column=0,
                    order=0,
                    layout="stacked",
                )
            )

        self.children.append(
            modules.AppList(_("Applications"), models=(f"{context['app_label']}.*",), column=0, order=1)
        )
