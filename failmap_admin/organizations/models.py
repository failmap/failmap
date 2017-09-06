# coding=UTF-8
# from __future__ import unicode_literals

from django.db import models
from django_countries.fields import CountryField
from jsonfield import JSONField
from django.core.exceptions import ValidationError


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
    twitter_handle = models.CharField(max_length=150,
                                      help_text="Include the @ symbol. "
                                                "Used in the top lists to let visitors tweet to the"
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
    area = JSONField(max_length=10000)

    class Meta:
        managed = True
        db_table = 'coordinate'


#  No cascade?
class Url(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    url = models.CharField(max_length=150)

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

    class Meta:
        managed = True
        db_table = 'url'
        unique_together = (('organization', 'url'),)

    def __str__(self):
        if self.is_dead:
            return "✝ %s" % self.url
        else:
            return self.url
