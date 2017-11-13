# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-11-09 22:43
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0003_auto_20171109_1427'),
    ]

    operations = [
        migrations.AlterField(
            model_name='job',
            name='result_id',
            field=models.CharField(blank=True, help_text='celery asyncresult ID for tracing task',
                                   max_length=255, null=True, unique=True),
        ),
    ]
