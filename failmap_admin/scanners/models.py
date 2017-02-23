from django.db import models


class ScansDnssec(models.Model):
    id = models.IntegerField(primary_key=True)
    url = models.CharField(max_length=150)
    has_dnssec = models.IntegerField()
    scanmoment = models.DateTimeField()
    rawoutput = models.TextField()

    class Meta:
        managed = True
        db_table = 'scans_dnssec'

    def __str__(self):
        return self.url


class ScansSsllabs(models.Model):
    url = models.CharField(max_length=255)
    servernaam = models.CharField(max_length=255)
    ipadres = models.CharField(max_length=255)
    poort = models.IntegerField()
    scandate = models.DateField()
    scantime = models.TimeField()
    scanmoment = models.DateTimeField()
    rating = models.CharField(max_length=3)
    ratingnotrust = models.CharField(db_column='ratingNoTrust', max_length=3)
    rawdata = models.TextField(db_column='rawData')
    isdead = models.IntegerField(db_column='isDead', default=False)
    isdeadsince = models.DateTimeField(
        db_column='isDeadSince', blank=True, null=True)
    isdeadreason = models.CharField(
        db_column='isDeadReason',
        max_length=255,
        blank=True,
        null=True)

    class Meta:
        managed = True
        db_table = 'scans_ssllabs'

    def __str__(self):
        return self.url
