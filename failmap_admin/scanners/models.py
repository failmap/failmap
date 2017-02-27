from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from .tasks import task_blascanner, task_store_scanresult


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


class ScansBla(models.Model):
    state = models.CharField(max_length=64, default='PENDING')
    task_id = models.CharField(max_length=128, null=True, blank=True)
    url = models.CharField(max_length=255)
    rating = models.CharField(max_length=3, blank=True)


@receiver(post_save, sender=ScansBla)
def dispatch_scan_task(sender, instance, **kwargs):
    """After creating and saving scansbla object, spawn a scan task."""

    # create task objects for scanning and storing the result
    scan_task = task_blascanner.s(instance.url)
    store_task = task_store_scanresult.s(sender.__name__, instance.id)
    # bind the tasks together, if the scan task is finished the result is passed to store_task
    task = (scan_task | store_task)

    # put the tasks on the queue, this returns result object which can be used
    # to get intermediate state
    async_result = task.apply_async()
    # store async_result for future reference
    sender.objects.filter(pk=instance.pk).update(task_id=async_result.id)
