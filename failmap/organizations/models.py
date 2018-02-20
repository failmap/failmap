# coding=UTF-8
# from __future__ import unicode_literals

import logging
from datetime import datetime, timedelta

import pytz
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from jsonfield import JSONField

logger = logging.getLogger(__package__)


class OrganizationType(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        managed = True

    def __str__(self):
        return self.name


def validate_twitter(value):
    if value[0:1] != "@":
        raise ValidationError('Twitter handle needs to start with an @ symbol.')


class Organization(models.Model):
    country = CountryField()
    type = models.ForeignKey(
        OrganizationType,
        on_delete=models.PROTECT,
        default=1)
    name = models.CharField(max_length=50)
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
    # todo: add default date for default ratings.
    # created_on = models.DateTimeField(
    #     blank=True,
    #     null=True
    # )

    # is_dead = models.BooleanField(
    #     default=False,
    #     help_text="A dead organization is not shown on the map, depending on the dead_date."
    # )

    # is_dead_since = models.DateTimeField(
    #     blank=True,
    #     null=True
    # )

    # is_dead_reason = models.CharField(
    #     max_length=255,
    #     blank=True,
    #     null=True
    # )

    def __unicode__(self):
        return u'%s  - %s in %s' % (self.name, self.type, self.country, )

    class Meta:
        managed = True
        db_table = 'organization'

    def __str__(self):
        return self.name


GEOJSON_TYPES = (
    ('MultiPolygon', 'MultiPolygon'),
    ('MultiLineString', 'MultiLineString'),
    ('MultiPoint', 'MultiPoint'),
    ('Polygon', 'Polygon'),
    ('LineString', 'LineString'),
    ('Point', 'Point'),
)


class Coordinate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    geojsontype = models.CharField(
        db_column='geoJsonType',
        max_length=20,
        blank=True,
        null=True,
        choices=GEOJSON_TYPES)
    area = JSONField(
        max_length=10000,
        help_text="GeoJson using the WGS84 (EPSG 4326) projection. Use simplified geometries to "
                  "reduce the amount of data to transfer."
    )

    class Meta:
        managed = True
        db_table = 'coordinate'


class Url(models.Model):
    organization_old = models.ForeignKey(Organization, null=True, on_delete=models.PROTECT)

    organization = models.ManyToManyField(Organization, related_name="u_many_o_upgrade")

    url = models.CharField(
        max_length=150,
        help_text="Lowercase url name. For example: mydomain.tld or subdomain.domain.tld"
    )

    created_on = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    not_resolvable = models.BooleanField(
        default=False,
        help_text="Url is not resolvable (anymore) and will not be picked up by scanners anymore."
                  "When the url is not resolvable, ratings from the past will still be shown(?)#")

    not_resolvable_since = models.DateTimeField(blank=True, null=True)

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
                  "something on this host.")

    onboarded = models.BooleanField(
        default=False,
        help_text="After adding a url, there is an onboarding process that runs a set of tests."
                  "These tests are usually run very quickly to get a first glimpse of the url."
                  "This test is run once.")

    onboarded_on = models.DateTimeField(auto_now_add=True, blank=True, null=True,
                                        help_text="The moment the onboard process finished.")

    class Meta:
        managed = True
        db_table = 'url'
        unique_together = (('organization_old', 'url'),)

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

    def is_top_level(self):
        # count the number of dots. Should be one.
        # allows your own extension on a lan. there are thousands of extensions today.
        # so do the stupid thing: trust user input :)
        if self.url.count(".") == 1:
            return True
        return False

    def add_subdomain(self, subdomain):
        # import here to prevent circular/cyclic imports, this module imports Url.
        from failmap.scanners.scanner_http import resolves

        new_url = (subdomain + "." + self.url).lower()

        if Url.objects.all().filter(url=new_url, organization__in=self.organization.all()).exists():
            logger.debug("Subdomain already in the database: %s" % new_url)
            return

        if not resolves(new_url):
            logger.debug("New subdomain did not resolve on either ipv4 and ipv6: %s" % new_url)
            return

        u = Url()
        # A Url needs to have a value for field "id" before a many-to-many relationship can be used.
        u.save()
        u.organization = self.organization.all()
        u.url = new_url
        u.save()
        logger.info("Added domain to database: %s" % new_url)

        # run standard checks, so you know the
        # discover_wildcards([u])

        return u

# are open ports based on IP adresses.
# adresses might change (and thus an endpoint changes).
# for the list of endpoints, you want to know what endpoints don't exist
# so they are not used anymore.
# class Port(models.Model):
#    url = models.ForeignKey(Url, on_delete=models.PROTECT)


def seven_days_in_the_future():
    return datetime.now(pytz.utc) + timedelta(days=7)


def today():
    return datetime.now(pytz.utc).today()


class Promise(models.Model):
    """Allow recording of organisation promises for improvement."""

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)

    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Context information about the promise (eg: ticket reference).")

    # https://stackoverflow.com/questions/29549611/fixed-default-value-provided-after-upgrading-to-django-1-8#29549675
    created_on = models.DateTimeField(
        default=today, blank=True, null=True)

    expires_on = models.DateTimeField(
        default=seven_days_in_the_future,
        blank=True,
        null=True,
        help_text="When in the future this promise is expected to be fulfilled.")

    def __str__(self):
        return '%s - %s' % (self.organization.name, self.created_on)
