import importlib
import logging
from datetime import datetime
from json import loads

import nested_admin
import pytz
import tldextract
from django import forms
from django.contrib import admin, messages
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline
from leaflet.admin import LeafletGeoAdminMixin

from websecmap import types
from websecmap.app.models import Job
from websecmap.celery import PRIO_HIGH, app
from websecmap.map.models import OrganizationReport
from websecmap.organizations import datasources
from websecmap.organizations.datasources import dutch_government, excel
from websecmap.organizations.models import (Coordinate, Dataset, Organization, OrganizationType,
                                            Promise, Url)
from websecmap.reporting.models import UrlReport
from websecmap.scanners import SCANNERS
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlGenericScan, UrlIp

log = logging.getLogger(__name__)


PROMISE_DESCRIPTION = """
<p>A 'promise' is an indication by an organisation representitive that an improvement
has been made which will alter the organizations score. A generic message will be
displayed on the organization report with the creation and expiry date of the promise
until it expires.</p>
<p>This indication is to overcome the problem of a negative score even though improvement
are made, but the score cannot reflect them yet due to technical or bureaucratic reasons.</p>
<p>It is not intended for long term promises of improvement that have not been applied or
put in to progress. The promised improvement must be verifiable by Faalkaart within a
handfull of days.</p>
"""


# todo: the through solution has two challenges:
# 1: the name of the objects listed
# 2: cannot auto-complete these with django-jet it seems, so an enormous amount of data
# it might be solved using an explicit relation?
# perhaps ask the django jet forum
class UrlAdminInline(CompactInline):
    model = Url.organization.through
    extra = 0
    show_change_link = False
    can_delete = False
    # 'is_dead',
    # For now not trying to fix the "through" relationship errors for getting fields from the URL object.
    # <class 'failmap.organizations.admin.UrlAdminInline'>: (admin.E035) The value of 'readonly_fields[1]' is not
    # a callable, an attribute of 'UrlAdminInline', or an attribute of 'organizations.Url_organization'.
    readonly_fields = ('url', )

    exclude = []


class OrganizationAdminInline(CompactInline):
    model = Organization
    extra = 0
    show_change_link = False
    can_delete = False
    readonly_fields = [f.name for f in Organization._meta.fields if f.name != 'id']

    exclude = []


# A highly limiting feature of the django admin interface is that inlines only
# go one level deep. Instead of N levels, and that nested inlines are not supported
# by default and all other support is experimental (or provides a severely reduced interface.
# https://github.com/theatlantic/django-nested-admin/ solves this, but misses support for the awesome compactinline
# a bug is that three empty values are added in the list below.
# perhaps the inline is fixable with some days of engineering, and might be worth while, but for now...
# and for some reason that
class EndpointGenericScanInline(nested_admin.NestedTabularInline):
    model = EndpointGenericScan

    can_delete = False

    exclude = ['domain', 'evidence', 'comply_or_explain_explained_on', 'comply_or_explain_case_handled_by',
               'comply_or_explain_explanation_valid_until', 'comply_or_explain_case_additional_notes',
               'comply_or_explain_explanation', 'comply_or_explain_explained_by'
               ]

    # this is purely informational, to save clicks when debugging.
    readonly_fields = ('comply_or_explain_is_explained',
                       'endpoint', 'type', 'rating', 'explanation', 'rating_determined_on', 'last_scan_moment',
                       'is_the_latest_scan')

    ordering = ['-rating_determined_on']

    verbose_name = "Generic scan"
    verbose_name_plural = "Generic scans"

    # @staticmethod
    # def rating_determined_on_date(obj):
    #     # todo: should be formatted in humanized form.
    #     return obj.rating_determined_on

    # @staticmethod
    # def last_scan_moment_date(obj):
    #     return obj.last_scan_moment

    def has_add_permission(self, request):
        return False


class EndpointAdminInline(nested_admin.NestedStackedInline):
    model = Endpoint
    extra = 0
    show_change_link = True
    ordering = ["is_dead"]
    inlines = [EndpointGenericScanInline]


class UrlGenericScanAdminInline(CompactInline):
    model = UrlGenericScan
    extra = 0
    show_change_link = True
    ordering = ["-rating_determined_on"]

    exclude = ['comply_or_explain_explained_on', 'comply_or_explain_case_handled_by',
               'comply_or_explain_explanation_valid_until', 'comply_or_explain_case_additional_notes',
               'comply_or_explain_explanation', 'comply_or_explain_explained_by', 'domain'
               ]

    readonly_fields = ('comply_or_explain_is_explained',
                       'type', 'rating', 'explanation', 'evidence', 'rating_determined_on',
                       'last_scan_moment', 'is_the_latest_scan')


class CoordinateAdminInline(CompactInline):
    model = Coordinate
    extra = 0


class OrganizationRatingAdminInline(CompactInline):
    model = OrganizationReport
    extra = 0
    readonly_fields = ('organization', 'high', 'medium', 'low', 'when', 'calculation')
    can_delete = False
    ordering = ["-when"]


class UrlRatingAdminInline(CompactInline):
    model = UrlReport
    extra = 0
    readonly_fields = ('url', 'high', 'medium', 'low', 'when', 'calculation')
    can_delete = False
    ordering = ["-when"]


class UrlIpInline(CompactInline):
    model = UrlIp
    extra = 0
    readonly_fields = ('url', 'ip', 'rdns_name', 'discovered_on', 'is_unused', 'is_unused_since', 'is_unused_reason')
    show_change_link = True
    ordering = ["-discovered_on"]


class PromiseAdminInline(CompactInline):
    model = Promise
    extra = 0
    ordering = ["-created_on"]

    fieldsets = (
        (None, {
            'fields': ('organization', 'created_on', 'expires_on', 'notes'),
            'description': PROMISE_DESCRIPTION,
        }),
    )


class ActionMixin:
    """Generic Mixin to add Admin Button for Organization/Url/Endpoint Actions.

    This class is intended to be added to ModelAdmin classes so all Actions are available without duplicating code.

    Action methods as described in:
      https://docs.djangoproject.com/en/2.0/ref/contrib/admin/actions/#actions-as-modeladmin-methods

    Most actions work on the same primary models (organization,url,endpoint). The Actions don't do any actual work but
    rather compose a task with the provided Queryset. After which this task is scheduled using a Job. This generic
    principle has been implemented in `generic_action` and the specific action implementations (eg; `scan_plain_http`)
    just provide the correct metadata (name, icon) and task composer to call.

    To keep up to date with all available scanners, function generators are used. For each scanner, when applicable,
    a function to perform a scan, verification or discovery. More scanners, mean more buttons.
    """

    # overrides the standard model class get_actions
    def get_actions(self, request):

        # using this function maker, scan functions can be generated.
        def scan_function_maker(scanner_name, verbose_name):

            def scan_function(self, *args, **kwargs):
                module = importlib.import_module('websecmap.scanners.scanner.%s' % scanner_name)
                return self.generic_action(module.compose_task, "🔬 %s" % verbose_name, *args, **kwargs)
            return scan_function

        def discover_function_maker(scanner_name, verbose_name):

            def scan_function(self, *args, **kwargs):
                module = importlib.import_module('websecmap.scanners.scanner.%s' % scanner_name)
                return self.generic_action(module.compose_discover_task, "🗺 %s" % verbose_name, *args, **kwargs)
            return scan_function

        def verify_function_maker(scanner_name, verbose_name):

            def verify_function(self, *args, **kwargs):
                module = importlib.import_module('websecmap.scanners.scanner.%s' % scanner_name)
                return self.generic_action(module.compose_verify_task, "[X] %s" % verbose_name, *args, **kwargs)
            return verify_function

        # this makes sure already existing actions are also returned
        actions = super().get_actions(request)

        for scanner in SCANNERS:
            # these discover:
            if scanner['can discover urls'] or scanner['can discover endpoints']:
                func = discover_function_maker(scanner['name'], scanner['verbose name'])
                unique_name = "discover_%s" % scanner['name']
                actions[unique_name] = (func, unique_name, '🗺 %s' % scanner['verbose name'])

        for scanner in SCANNERS:
            # these verify:
            if scanner['can verify urls'] or scanner['can verify endpoints']:
                func = verify_function_maker(scanner['name'], scanner['verbose name'])
                unique_name = "verify_%s" % scanner['name']
                actions[unique_name] = (func, unique_name, '[X] %s' % scanner['verbose name'])

        for scanner in SCANNERS:
            # these create scans
            if scanner['creates endpoint scan types'] or scanner['creates url scan types']:
                func = scan_function_maker(scanner['name'], scanner['verbose name'])
                unique_name = "scan_%s" % scanner['name']
                actions[unique_name] = (func, unique_name, '🔬 %s' % scanner['verbose name'])

        return actions

    def generic_action(self, task_composer: types.compose_task, name: str, request, queryset):
        """Admin action that will create a Job of tasks."""

        filters = {'x_filter': {'id__in': queryset.values_list('id')}}
        if queryset.model == Organization:
            filters['organizations_filter'] = filters.pop('x_filter')
        elif queryset.model == Url:
            filters['urls_filter'] = filters.pop('x_filter')
        elif queryset.model == Endpoint:
            filters['endpoints_filter'] = filters.pop('x_filter')

        task = task_composer(**filters)
        task_name = "%s (%s) " % (name, ','.join(map(str, list(queryset))))
        job = Job.create(task, task_name, request, priority=PRIO_HIGH)
        link = reverse('admin:app_job_change', args=(job.id,))
        self.message_user(request, 'Job created, <a href="%s">%s</a>' % (link, task_name))


# http://jet.readthedocs.io/en/latest/autocomplete.html?highlight=many
# for many values in the admin interface... for example endpoints.
@admin.register(Organization)
class OrganizationAdmin(ActionMixin, ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name_details', 'type', 'country', 'wikidata_', 'wikipedia_', 'created_on', 'is_dead')
    search_fields = (['name', 'country', 'type__name'])
    list_filter = ['type__name', 'country', 'created_on', 'is_dead', 'is_dead_since'][::-1]

    fields = ('name', 'type', 'country', 'internal_notes', 'twitter_handle', 'created_on', 'wikidata', 'wikipedia',
              'is_dead', 'is_dead_since', 'is_dead_reason')

    inlines = [CoordinateAdminInline, UrlAdminInline, OrganizationRatingAdminInline, PromiseAdminInline]  #

    @staticmethod
    def name_details(self):
        if self.is_dead:
            return "✝ %s, %s (%s - %s)" % (self.name, self.country,
                                           self.created_on.strftime("%b %Y") if self.created_on else "",
                                           self.is_dead_since.strftime("%b %Y") if self.is_dead_since else "")
        else:
            return "%s, %s (%s)" % (self.name, self.country, self.created_on.strftime("%b %Y"))

    @staticmethod
    def wikidata_(self):
        return format_html("<a href='https://www.wikidata.org/wiki/%s' target='_blank'>🔍 %s</a>" %
                           (self.wikidata, self.wikidata))

    @staticmethod
    def wikipedia_(self):
        return format_html("<a href='https://www.wikipedia.org/wiki/%s' target='_blank'>🔍 %s</a>" %
                           (self.wikipedia, self.wikipedia))

    # preserve_filters = True


# https://docs.djangoproject.com/en/2.0/ref/forms/validation/
class MyUrlAdminForm(forms.ModelForm):

    def clean_url(self):

        url_string = self.data.get("url")

        # urls must be lowercase
        url_string = url_string.lower()

        # todo: remove invalid characters
        # Currently assume that there is some sense in adding this data.

        # see if the url is complete, and remove the http(s):// and paths parts:
        result = tldextract.extract(url_string)

        if result.subdomain:
            clean_url_string = "%s.%s.%s" % (result.subdomain, result.domain, result.suffix)
        else:
            clean_url_string = "%s.%s" % (result.domain, result.suffix)

        # also place the cleaned data back into the form, in case of errors.
        # this does not work this way it seems.
        # self.data.url = clean_url_string

        if not result.suffix:
            raise ValidationError("Url is missing suffix (.com, .net, ...)")

        return clean_url_string

    def clean(self):
        organizations = self.cleaned_data.get("organization")

        # mandatoryness error will already be triggered, don't interfere with that.
        if not organizations:
            return

        log.error(self.cleaned_data)
        # make sure the URL is not added if it is already alive and matched to the selected organization.
        # except yourself of course...
        # todo: expemt yourself, .exclude(pk=self.cleaned_data.get("pk"))
        for organization in organizations:
            if Url.objects.all().filter(
                    url=self.cleaned_data.get("url"), is_dead=False,
                    organization=organization).count() > 1:

                # format_html = XSS :)
                raise ValidationError(format_html(_(
                    'Url %(url)s is already matched to "%(organization)s", and is alive. '
                    'Please add any remaining organizations to the existing version of this url. '
                    'Search for <a href="../?url=%(url)s&is_dead=False">🔍 %(url)s</a>.'
                    % {'url': self.cleaned_data.get("url"), 'organization': organization})))

        # make sure the Url is not added if it is still alive: the existing url should be edited and the
        # organization should be added. (we might be able to do this automatically since we know the url is not
        # already matched to an organization) - In that case all other fields have to be ignored and
        # this form still closes succesfully.
        # This url already exists and the selected organization(s) have been added to it.

        if Url.objects.all().filter(
                url=self.data.get("url"), is_dead=False).count() > 1:

            # format_html = XSS :)
            raise ValidationError(format_html(_(
                'This url %(url)s already exists and is alive. Please add the desired organizations to the existing '
                'url. This was not done automatically because it might be possible specific other data was entered in '
                'this form that cannot blindly be copied (as it might interfere with the existing url). '
                'Search for <a href="../?url=%(url)s&is_dead=False">🔍 %(url)s</a>.'
                % {'url': self.data.get("url")})))


class HasEndpointScansListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Has endpoint scans (todo)')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'endpoint_scans'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # todo: make this filter work
        if self.value() == 'yes':
            return queryset
        if self.value() == 'no':
            return queryset


@admin.register(Url)
class UrlAdmin(ActionMixin, ImportExportModelAdmin, nested_admin.NestedModelAdmin):
    form = MyUrlAdminForm

    list_display = ('url', 'sub', 'domain', 'tld',
                    'visit', 'current_rating', 'onboarded', 'onboarding_stage', 'uses_dns_wildcard',
                    'dead_for', 'unresolvable_for', 'created_on')

    search_fields = ('url', 'computed_subdomain', 'computed_domain', 'computed_suffix')
    list_filter = ['is_dead', 'is_dead_since', 'is_dead_reason',
                   'not_resolvable', 'not_resolvable_since', 'not_resolvable_reason',
                   'uses_dns_wildcard', 'organization', 'onboarded', 'onboarding_stage', 'organization__type__name',
                   'organization__country', 'dns_supports_mx',
                   HasEndpointScansListFilter][::-1]

    fieldsets = (
        (None, {
            'fields': ('url', 'organization', 'internal_notes', 'created_on', 'onboarded', 'onboarding_stage')
        }),
        ('DNS', {
            'fields': ('do_not_find_subdomains', 'uses_dns_wildcard', 'dns_supports_mx', ),
        }),
        ('Resolvability', {
            'description': 'Non resolving urls cannot be reached anymore.',
            'fields': ('not_resolvable', 'not_resolvable_since', 'not_resolvable_reason'),
        }),
        ('dead URL management', {
            'description': "Dead urls are not show on the map. They can be dead on layer 8 (for example when a "
                           "wildcard DNS is used, but not a matching TLS certificate as wildcard certificates "
                           "are rarely used due to drawbacks).",
            'fields': ('is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
        ('computed', {
            'description': 'These values are automatically computed on save. Do not modify them by hand.',
            'fields': ('computed_subdomain', 'computed_domain', 'computed_suffix')
        })
    )
    readonly_fields = ['created_on']

    @staticmethod
    def domain(obj):
        return obj.computed_domain

    @staticmethod
    def tld(obj):
        return obj.computed_suffix

    @staticmethod
    def sub(obj):
        return obj.computed_subdomain

    # save a ton of queries
    # doesn't work with sets.
    # https://docs.djangoproject.com/en/2.1/ref/contrib/admin/
    # list_select_related = ('endpoint_set', )

    def visit(self, obj: Url):
        if not obj.endpoint_set.count():
            return

        str = format_html("%s <a href='/admin/scanners/endpoint/?q=%s' target='_blank'>🔍</a>" %
                          (obj.endpoint_set.count(), obj.url))

        for endpoint in obj.endpoint_set.all():

            if endpoint.is_dead is False:
                str += " - <a href='%(protocol)s://%(url)s:%(port)s' target='_blank'>%(protocol)s/%(port)s</a>" % {
                    'url': obj.url,
                    'port': endpoint.port,
                    'protocol': endpoint.protocol
                }
        return format_html(str)

    @staticmethod
    def unresolvable_for(self):
        if self.not_resolvable and self.not_resolvable_since:
            return naturaltime(self.not_resolvable_since)
        else:
            return "-"

    # todo: further humanize this.
    @staticmethod
    def dead_for(self):
        if self.is_dead and self.is_dead_since:
            return naturaltime(self.is_dead_since)
        else:
            return "-"

    @staticmethod
    def current_rating(obj):
        x = UrlReport.objects.filter(url=obj).latest('when')

        if not any([x.high, x.medium, x.low]):
            return "✅ Perfect"

        label = "🔴" if x.high else "🔶" if x.medium else "🍋"

        return format_html("%s <span style='color: red'>%s</span> <span style='color: orange'>%s</span> "
                           "<span style='color: yellow'>%s</span>" % (label, x.high, x.medium, x.low))

    inlines = [UrlGenericScanAdminInline, EndpointAdminInline, UrlRatingAdminInline, UrlIpInline]

    actions = []

    # saved here in case we want to go back.
    # def onboard(self, request, queryset):
    #     onboard_urls(urls=list(queryset))
    #     self.message_user(request,
    #         "Onboarding task has been added. Onboarding can take a while depending on server load.")
    # actions.append('onboard')
    # onboard.short_description = "🔮  Onboard"

    def declare_dead(self, request, queryset):
        for url in queryset:
            url.is_dead = True
            url.is_dead_reason = "Killed via admin interface"
            url.is_dead_since = datetime.now(pytz.utc)
            url.save()
        self.message_user(request, "Declare dead: Done")
    declare_dead.short_description = "🔪  Declare dead"
    actions.append('declare_dead')

    def timeline_debug(self, request, queryset):
        from websecmap.reporting.report import create_timeline, inspect_timeline
        from django.http import HttpResponse

        content = "<pre>"
        for url in queryset:
            content += inspect_timeline(create_timeline(url), url)

        content += "</pre>"

        return HttpResponse(content)
    timeline_debug.short_description = "🐞  Timeline"
    actions.append('timeline_debug')


@admin.register(OrganizationType)
class OrganizationTypeAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('name', )
    search_fields = ('name', )
    list_filter = ('name', )
    fields = ('name', )

    inlines = [OrganizationAdminInline]


@admin.register(Coordinate)
class CoordinateAdmin(LeafletGeoAdminMixin, ImportExportModelAdmin):

    # show Europe as default. Will probably change over time.
    # http://django-leaflet.readthedocs.io/en/latest/advanced.html
    # If you copy this setting from a point, be sure to switch x and y when pasting in default center.
    settings_overrides = {
        'DEFAULT_CENTER': (51.376378068613406, 13.223944902420046),
        'DEFAULT_ZOOM': 4
    }

    list_display = ('id', 'organization', 'geojsontype', 'created_on', 'is_dead', 'area')
    search_fields = ('organization__name', 'geojsontype')
    list_filter = ['organization__type', 'organization__country', 'organization', 'geojsontype', 'created_on',
                   'is_dead', 'is_dead_since'][::-1]

    # We wanted to place these on another tab, otherwise leaflet blocks mouse scrolling (which is annoying).
    # But then leaflet doesn't initialize properly, making the map unworkable. So they're on the first tab anyway.
    fieldsets = (
        (None, {
            'description': "The Edit area makes it easier to manipulate the Area and Geojsontype. Yet: when both are "
                           "changed, the Area/GeoJsontype takes precedence."
                           ""
                           "If you want to move the coordinate, preferably do so by creating a new one and setting the"
                           " current one as dead (+date etc). Then the map will show coordinates over time, which is "
                           "pretty neat.",
            'fields': ('organization', 'geojsontype', 'area', 'edit_area', 'creation_metadata')
        }),

        ('Life cycle', {
            'fields': ('created_on', 'is_dead', 'is_dead_since', 'is_dead_reason'),
        }),
    )

    actions = []

    def switch_lnglat(self, request, queryset):
        for coordinate in queryset:

            if coordinate.geojsontype != "Point":
                continue

            a = coordinate.area
            coordinate.area = [a[1], a[0]]

            coordinate.edit_area = {
                "type": "Point",
                "coordinates": [a[1], a[0]]
            }

            coordinate.save()
        self.message_user(request, "Lng Lat switched. Order should be: Lng, Lat.")
    switch_lnglat.short_description = "Switch Lng Lat"
    actions.append('switch_lnglat')

    def save_model(self, request, obj, form, change):

        # log.info(form.changed_data)
        # grrr, both area and edit_area are ALWAYS changed... even if you didn't change the values in these
        # fields... this is obviously a bug or "optimization". We now have to resort to queries to figure out
        # if anything changed at all. Evil bugs.

        if obj.pk:
            # we're changing the object
            current = Coordinate.objects.get(pk=obj.pk)

            if current.area != obj.area or current.geojsontype != obj.geojsontype:
                # if 'area' in form.changed_data or 'geojsontype' in form.changed_data: doesn't work.
                log.info("area changed")
                edit_area = {"type": form.cleaned_data['geojsontype'],
                             "coordinates": form.cleaned_data['area']}
                obj.edit_area = edit_area

            elif current.edit_area != obj.edit_area:
                log.info("edit area changed")
                log.info(form.cleaned_data["edit_area"])
                obj.geojsontype = form.cleaned_data["edit_area"]["type"]
                obj.area = form.cleaned_data["edit_area"]["coordinates"]
        else:
            # new object... see if there are empty fields we can ammend:
            if (not obj.area or not obj.geojsontype) and obj.edit_area:
                obj.geojsontype = form.cleaned_data["edit_area"]["type"]
                obj.area = form.cleaned_data["edit_area"]["coordinates"]
            elif not obj.edit_area:
                edit_area = {"type": form.cleaned_data['geojsontype'],
                             "coordinates": form.cleaned_data['area']}
                obj.edit_area = edit_area

        super().save_model(request, obj, form, change)


@admin.register(Promise)
class PromiseAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('organization', 'created_on', 'expires_on')
    search_fields = ('organization',)
    list_filter = ('organization',)

    fieldsets = (
        (None, {
            'fields': ('organization', 'created_on', 'expires_on', 'notes'),
            'description': PROMISE_DESCRIPTION,
        }),
    )


class DatasetForm(forms.ModelForm):

    def clean_kwargs(self):
        value = self.cleaned_data['kwargs']
        try:
            loads(value)
        except ValueError as exc:
            raise forms.ValidationError(
                _('Unable to parse JSON: %s') % exc,
            )

        return value


@admin.register(Dataset)
# todo: how to show a form / allowing uploads?
class DatasetAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ('id', 'url_source', 'file_source', 'type', 'is_imported', 'imported_on')
    search_fields = ('url_source', )
    list_filter = ('is_imported', 'imported_on')
    fields = ('url_source', 'file_source', 'type', 'kwargs', 'is_imported', 'imported_on')

    actions = []

    # todo: perhaps a type should be added, and that defines what importer is used here...
    # Then we also need the options to be expanded with options from the database.

    def import_(self, request, queryset):

        # check if the environment is sane, if not, return a user message with the error
        try:
            datasources.check_environment()
        except BaseException as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return

        for dataset in queryset:
            kwargs = {'url': dataset.url_source, 'file': dataset.file_source}

            extra_kwargs = loads(dataset.kwargs)
            kwargs = {**kwargs, **extra_kwargs}

            # ok, it's not smart to say something is imported before it has been verified to be imported.
            importers = {
                'excel': excel,
                'dutch_government': dutch_government,
                '': excel,
                None: excel
            }

            if not importers.get(dataset.type, None):
                raise ValueError('Datasource parser for %s is not available.' % dataset.type)

            (importers[dataset.type].import_datasets.si(**kwargs)
             | dataset_import_finished.si(dataset)).apply_async()
        self.message_user(request, "Import started, will run in parallel.")
    import_.short_description = "+ Import"
    actions.append('import_')

    form = DatasetForm

    save_as = True
    preserve_filters = True


@app.task(queue='storage')
def dataset_import_finished(dataset):
    dataset.is_imported = True
    dataset.imported_on = datetime.now(pytz.utc)
    dataset.save()
