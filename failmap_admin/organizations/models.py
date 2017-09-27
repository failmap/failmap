# coding=UTF-8
# from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.db import models
from django_countries.fields import CountryField
from jsonfield import JSONField


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


#  No cascade?
class Url(models.Model):
    organization = models.ForeignKey(Organization)  # on_delete=models.PROTECT

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
        db_column='isDead',
        default=False,
        help_text="Dead url's will not be rendered on the map. Scanners can set this check "
                  "automatically (which might change in the future)")
    is_dead_since = models.DateTimeField(
        db_column='isDeadSince', blank=True, null=True)
    is_dead_reason = models.CharField(
        db_column='isDeadReason',
        max_length=255,
        blank=True,
        null=True)

    uses_dns_wildcard = models.BooleanField(
        default=False,
        help_text="When true, this domain uses a DNS wildcard and any subdomain will resolve to "
                  "something on this host.")

    class Meta:
        managed = True
        db_table = 'url'
        unique_together = (('organization', 'url'),)

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

# are open ports based on IP adresses.
# adresses might change (and thus an endpoint changes).
# for the list of endpoints, you want to know what endpoints don't exist
# so they are not used anymore.
# class Port(models.Model):
#    url = models.ForeignKey(Url, on_delete=models.PROTECT)
