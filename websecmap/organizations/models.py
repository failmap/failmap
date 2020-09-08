# coding=UTF-8
# from __future__ import unicode_literals

import hashlib
import logging
from datetime import datetime, timedelta

import pytz
import tldextract
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from jsonfield import JSONField
from validators import domain

log = logging.getLogger(__package__)


class OrganizationType(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("layer"))

    class Meta:
        managed = True
        verbose_name = _('layer')
        verbose_name_plural = _('layers')

    def __str__(self):
        return self.name


def validate_twitter(value):
    if value[0:1] != "@":
        raise ValidationError('Twitter handle needs to start with an @ symbol.')


class Organization(models.Model):
    country = CountryField(db_index=True)

    type = models.ForeignKey(
        OrganizationType,
        on_delete=models.PROTECT,
        default=1)

    name = models.CharField(max_length=250, db_index=True)

    computed_name_slug = models.SlugField(
        max_length=250,
        help_text="Computed value, a slug translation of the organization name, which can be used in urls.",
        default="",
    )

    internal_notes = models.TextField(
        max_length=2500,
        help_text="These notes can contain information on WHY this organization was added. Can be handy if it's not "
                  "straightforward. This helps with answering questions why the organization was added lateron. "
                  "These notes will not be published, but are also not secret.",
        blank=True,
        null=True,
    )

    twitter_handle = models.CharField(
        max_length=150,
        help_text="Include the @ symbol. Used in the top lists to let visitors tweet to the"
                  "organization to wake them up.",
        null=True,
        blank=True,
        validators=[validate_twitter]
    )

    # stacking is_dead pattern
    # postpone migration on production.
    created_on = models.DateTimeField(
        blank=True,
        null=True,
        default=datetime(year=2016, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc),
        db_index=True
    )

    is_dead_since = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True
    )

    is_dead = models.BooleanField(
        default=False,
        help_text="A dead organization is not shown on the map, depending on the dead_date."
    )

    is_dead_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    wikidata = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Reference to the wikidata project. Example:Q9928"
    )

    wikipedia = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Reference to the wikipedia article, including the correct wiki. "
                  "Example: nl:Heemstede (Noord-Holland)"
    )

    surrogate_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Any ID used to identify this organization in an external system. Used in automated imports via "
                  "the API. Otherwise leave this field empty."
    )

    class Meta:
        managed = True
        db_table = 'organization'
        verbose_name = _('organization')
        verbose_name_plural = _('organizations')

    # todo: find a smarter way to get the organization type name, instead of a related query... cached enums?
    # this list resets per restart. So if you do complex changes in these layers / types...
    organization_name_cache = {}

    def __str__(self):

        if self.type_id not in self.organization_name_cache:
            # log.debug("caching...")
            self.organization_name_cache[self.type_id] = self.type.name

        type_label = self.organization_name_cache[self.type_id]

        if self.is_dead:
            return "✝ %s, %s/%s (%s)" % (self.name, self.country, type_label, self.created_on.strftime("%b %Y"))
        else:
            return "%s, %s/%s (%s)" % (self.name, self.country, type_label, self.created_on.strftime("%b %Y"))

    def add_url(self, url: str):

        # add url to database with validation etc:
        url = Url.add(url)

        # then add it to the organization
        url.organization.add(self)
        url.save()

    def save(self, *args, **kwarg):

        # handle computed values
        self.computed_name_slug = slugify(self.name)
        super(Organization, self).save(*args, **kwarg)


GEOJSON_TYPES = (
    ('MultiPolygon', 'MultiPolygon'),
    ('MultiLineString', 'MultiLineString'),
    ('MultiPoint', 'MultiPoint'),
    ('Polygon', 'Polygon'),
    ('LineString', 'LineString'),
    ('Point', 'Point'),
)


class Coordinate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    geojsontype = models.CharField(
        db_column='geoJsonType',
        max_length=20,
        blank=True,
        null=True,
        choices=GEOJSON_TYPES)

    # Note that points are stored in lng, lat format
    # https://gis.stackexchange.com/questions/54065/leaflet-geojson-coordinate-problem
    area = JSONField(
        max_length=10000,
        blank=True,
        help_text="GeoJson using the WGS84 (EPSG 4326) projection. Use simplified geometries to "
                  "reduce the amount of data to transfer. Editing both this and the edit_area, this will take "
                  "preference."
    )

    # 9e107d9d372bb6826bd81d3542a419d6 (16 bytes, or a string of 32 characters)
    calculated_area_hash = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Automatically calculated hash of the area field using the MD5 algorithm. This is used to"
                  " try and optimize grouping on area (which is a very long text field, which is slow). The "
                  " hope is that this field will increase the speed of which grouping happens. If it doesn't, "
                  " we could calculate an even simpler hash by using the date + organization name."
                  " Note that if only one field is used for an organization (multipolygon, etc) "
                  "this field is not required... We still developed it because we forgot what we made..."
    )

    edit_area = JSONField(
        max_length=10000,
        null=True,
        blank=True,
        help_text="The results of this field are saved in the area and geojsontype. It's possible to edit the area"
                  " field directly, which overwrites this field. Changing both the manual option takes preference."
    )

    # stacking pattern for coordinates.
    created_on = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        default=datetime(year=2016, month=1, day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=pytz.utc)
    )
    creation_metadata = models.CharField(
        max_length=255,
        blank=True,
        null=True)
    is_dead = models.BooleanField(
        default=False,
        help_text="Dead url's will not be rendered on the map. Scanners can set this check "
                  "automatically (which might change in the future)")
    is_dead_since = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True
    )
    is_dead_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    def save(self, *args, **kwarg):
        # handle computed values
        self.calculated_area_hash = hashlib.md5(str(self.area).encode('utf-8')).hexdigest()
        super(Coordinate, self).save(*args, **kwarg)

    class Meta:
        managed = True
        db_table = 'coordinate'
        verbose_name = _('coordinate')
        verbose_name_plural = _('coordinates')


class Url(models.Model):
    organization = models.ManyToManyField(
        Organization,
        related_name="u_many_o_upgrade"
    )

    url = models.CharField(
        max_length=255,
        help_text="Lowercase url name. For example: mydomain.tld or subdomain.domain.tld"
    )

    internal_notes = models.TextField(
        max_length=500,
        help_text="These notes can contain information on WHY this URL was added. Can be handy if it's not "
                  "straightforward. This helps with answering questions why the URL was added lateron. For example: "
                  "some urls are owned via a 100% shareholder construction by a state company / municipality "
                  "while the company itself is private. These notes will not be published, but are also not secret.",
        blank=True,
        null=True,
    )

    created_on = models.DateTimeField(
        auto_now_add=True,
        blank=True,
        null=True
    )

    not_resolvable = models.BooleanField(
        default=False,
        help_text="Url is not resolvable (anymore) and will not be picked up by scanners anymore."
                  "When the url is not resolvable, ratings from the past will still be shown(?)#")

    not_resolvable_since = models.DateTimeField(
        blank=True,
        null=True
    )

    not_resolvable_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="A scanner might find this not resolvable, "
                  "some details about that are placed here."
    )

    is_dead = models.BooleanField(
        default=False,
        help_text="Dead url's will not be rendered on the map. Scanners can set this check "
                  "automatically (which might change in the future)"
    )

    is_dead_since = models.DateTimeField(
        blank=True, null=True
    )

    is_dead_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    uses_dns_wildcard = models.BooleanField(
        default=False,
        help_text="When true, this domain uses a DNS wildcard and any subdomain will resolve to "
                  "something on this host."
    )

    do_not_find_subdomains = models.BooleanField(
        default=False,
        help_text="If you do not want to automatically find subdomains, check this. This might be useful when "
                  "a very, very large number of subdomains will be added for an organization and you only want to "
                  "monitor a few urls that are relevant."
    )

    dns_supports_mx = models.BooleanField(
        default=False,
        help_text="If there is at least one MX record available, so we can perform mail generic mail scans. (for these"
                  "scans we don't need to know what mail-ports and protocols/endpoints are available).")

    onboarding_stage = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="Because of complexity of onboarding, not working with Celery properly, onboarding is done in "
                  "multiple steps. The last completed step is saved in this value. Empty: nothing. endpoints: endpoints"
                  " have been found. completed: onboarding is done, also onboarded flag is set."
    )

    computed_subdomain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Automatically computed by tldextract on save. Data entered manually will be overwritten.",
        db_index=True
    )

    computed_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Automatically computed by tldextract on save. Data entered manually will be overwritten."
    )

    computed_suffix = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Automatically computed by tldextract on save. Data entered manually will be overwritten."
    )

    onboarding_stage_set_on = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the onboarding stage was hit. Helps with time-outs."
    )

    onboarded = models.BooleanField(
        default=False,
        help_text="After adding a url, there is an onboarding process that runs a set of tests."
                  "These tests are usually run very quickly to get a first glimpse of the url."
                  "This test is run once.")

    onboarded_on = models.DateTimeField(
        blank=True,
        null=True,
        help_text="The moment the onboard process finished."
    )

    class Meta:
        managed = True
        db_table = 'url'

    def __str__(self):
        if self.is_dead:
            return "✝ %s" % self.url
        else:
            return self.url

    def make_unresolvable(self, message, date):
        self.not_resolvable = True
        self.not_resolvable_reason = message
        self.not_resolvable_since = date
        self.save()

    def clean(self):

        if self.is_dead and (not self.is_dead_since or not self.is_dead_reason):
            raise ValidationError(_('When telling this is dead, also enter the date and reason for it.'))

        if Url.objects.all().filter(url=self.url, is_dead=False, not_resolvable=False).exclude(pk=self.pk).exists():
            raise ValidationError(_('Url already exists, existing url is alive and resolvable.'))

        # urls must be lowercase
        self.url = self.url.lower()

        # !!!! below validation was placed in the admin interface.
        # We're adding the URL before we know it's allowed. This due to the missing docs on how to clean
        # many to many relationships. The URL needs to have an ID when querying a many to many for it, otherwise
        # you'll get an exception.
        # If it already exists, the url will be deleted still.
        # https://code.djangoproject.com/ticket/12938 - NOPE, not going to happen...
        # so we use plain old SQL and then it works fine :)
        # And that also won't work because organization is empty. Which is a total bummer. You'd expect
        # this field to be here somehow, but it isn't.
        # a warning might be possible after the insert, but then you've got two urls already.
        # this is really a shortcoming of Django.

    def save(self, *args, **kwarg):

        # handle computed values

        result = tldextract.extract(self.url)
        self.computed_subdomain = result.subdomain
        self.computed_domain = result.domain
        self.computed_suffix = result.suffix

        super(Url, self).save(*args, **kwarg)

    def is_top_level(self):
        # count the number of dots. Should be one.
        # allows your own extension on a lan. there are thousands of extensions today.
        # so do the stupid thing: trust user input :)
        if self.url.count(".") == 1:
            return True
        return False

    @transaction.atomic
    def add_subdomain(self, subdomain):
        # import here to prevent circular/cyclic imports, this module imports Url.
        from websecmap.scanners.scanner.http import resolves

        if not subdomain:
            return

        new_url = (subdomain + "." + self.url).lower()

        if not Url.is_valid_url(new_url):
            log.debug("Subdomain not valid: %s" % new_url)
            return

        if Url.objects.all().filter(url=new_url, organization__in=self.organization.all()).exists():
            log.debug("Subdomain already in the database: %s" % new_url)
            return

        if not resolves(new_url):
            log.debug("New subdomain did not resolve on either ipv4 and ipv6: %s" % new_url)
            return

        # we found something that gives the idea that transactions are not working.
        u, created = Url.objects.get_or_create(url=new_url)
        if not created:
            log.warning("The url already existed in the database, even while all prior checks in "
                        "this transaction told us otherwise.")

        # A Url needs to have a value for field "id" before a many-to-many relationship can be used.
        for organization in self.organization.all():
            u.organization.add(organization)
            u.save()
            log.info("Added url: %s to organization: %s" % (new_url, organization))

        return u

    @staticmethod
    def is_valid_url(url: str):

        # empty strings, etc
        if not url:
            return False

        extract = tldextract.extract(url)
        if not extract.suffix:
            return False

        # Validators catches 'most' invalid urls, but there are some issues and exceptions that are not really likely
        # to cause any major issues in our software. The other alternative is another library with other quircks.
        # see: https://github.com/kvesteri/validators/
        # Note that this library does not account for 'idna' / punycode encoded domains, so you have to convert
        # them yourself. luckily:
        # 'аренда.орг' -> 'xn--80aald4bq.xn--c1avg'
        # 'google.com' -> 'google.com'
        valid_domain = domain(url.encode('idna').decode())
        if valid_domain is not True:
            return False

        return True

    @staticmethod
    def add(url: str):

        if not Url.is_valid_url(url):
            raise ValueError("Url is not valid. It does not follow idna spec or does not have a valid suffix. "
                             "IP Addresses are not valid at this moment.")

        existing_url = Url.objects.all().filter(url=url, is_dead=False).first()
        if not existing_url:
            new_url = Url(url=url)
            new_url.created_on = datetime.now(pytz.utc)
            new_url.save()
            return new_url

        return existing_url


def seven_days_in_the_future():
    return datetime.now(pytz.utc) + timedelta(days=7)


def today():
    return datetime.now(pytz.utc).today()


class Dataset(models.Model):
    """
    Allows you to define URL datasources to download and import into the system. This acts as a memory of what you
    have imported. You can even re-import the things listed here. It will use the generic/excel importer.
    """
    url_source = models.URLField(
        null=True,
        blank=True,
        help_text="Fill out either the URL or File source. - A url source hosts the data you wish to process, this "
                  "can be an excel file. You can also upload the excel file below. This works great with online data "
                  "sources that are published regularly. Make sure the parser exists as you cannot process any "
                  "arbritrary download."
    )

    file_source = models.FileField(
        null=True,
        blank=True,
        help_text="Fill out either the URL or File source. - "
                  "A file upload has to be in a specific Excel format. You can download this format here: "
                  "<a href='/static/websecmap/empty_organizations_import_file.xlsx'>empty file</a>. "
                  "You can also download "
                  "an example that shows how to enter the data correctly. You can download the example here: "
                  "<a href='/static/websecmap/example_organizations_import_file.xlsx'>example file</a>"
    )

    is_imported = models.BooleanField(default=False,)
    imported_on = models.DateTimeField(blank=True, null=True)
    type = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        choices=[("excel", "Excel"), ("dutch_government", "Dutch Government")],
        help_text="To determine what importer is needed.",
        default='excel'
    )

    kwargs = models.TextField(
        max_length=5000,
        blank=True,
        null=True,
        help_text="A JSON / dictionary with extra options for the parser to handle the dataset. "
                  "This is different per parser. This field is highly coupled with the code of the parser.",
        default='{}'
    )
