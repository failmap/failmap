from __future__ import unicode_literals

from django.db import models
from django_countries.fields import CountryField

# Create your models here.
# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey has `on_delete` set to the desired behavior.
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.


class Organization(models.Model):
    country = CountryField()
    type = models.CharField(max_length=40)
    name = models.CharField(max_length=50)

    def __unicode__(self):
        return u'%s  - %s in %s' % (self.name, self.type, self.country, )

    class Meta:
        managed = True
        db_table = 'organization'



class Coordinate(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    geojsontype = models.CharField(db_column='geoJsonType', max_length=20, blank=True, null=True)  # Field name made lowercase.
    area = models.CharField(max_length=10000)

    class Meta:
        managed = True
        db_table = 'coordinate'



class ScansDnssec(models.Model):
    id = models.IntegerField(primary_key=True)
    url = models.CharField(max_length=150)
    has_dnssec = models.IntegerField()
    scanmoment = models.DateTimeField()
    rawoutput = models.TextField()

    class Meta:
        managed = True
        db_table = 'scans_dnssec'


class ScansSsllabs(models.Model):
    url = models.CharField(max_length=255)
    servernaam = models.CharField(max_length=255)
    ipadres = models.CharField(max_length=255)
    poort = models.IntegerField()
    scandate = models.DateField()
    scantime = models.TimeField()
    scanmoment = models.DateTimeField()
    rating = models.CharField(max_length=3)
    ratingnotrust = models.CharField(db_column='ratingNoTrust', max_length=3)  # Field name made lowercase.
    rawdata = models.TextField(db_column='rawData')  # Field name made lowercase.
    isdead = models.IntegerField(db_column='isDead')  # Field name made lowercase.
    isdeadsince = models.DateTimeField(db_column='isDeadSince')  # Field name made lowercase.
    isdeadreason = models.CharField(db_column='isDeadReason', max_length=255)  # Field name made lowercase.

    class Meta:
        managed = True
        db_table = 'scans_ssllabs'



# missing on update, so updates can cascade through the model. That is excellent for merges.
class Url(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    url = models.CharField(max_length=150)
    isdead = models.BooleanField(db_column='isDead', default=False)  # Field name made lowercase.
    isdeadsince = models.DateTimeField(db_column='isDeadSince', blank=True, null=True)  # Field name made lowercase.
    isdeadreason = models.CharField(db_column='isDeadReason', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = True
        db_table = 'url'
        unique_together = (('organization', 'url'),)
