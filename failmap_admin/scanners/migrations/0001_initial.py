# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-23 00:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ScansDnssec',
            fields=[
                ('id', models.IntegerField(primary_key=True, serialize=False)),
                ('url', models.CharField(max_length=150)),
                ('has_dnssec', models.IntegerField()),
                ('scanmoment', models.DateTimeField()),
                ('rawoutput', models.TextField()),
            ],
            options={
                'managed': True,
                'db_table': 'scans_dnssec',
            },
        ),
        migrations.CreateModel(
            name='ScansSsllabs',
            fields=[
                ('id', models.AutoField(auto_created=True,
                                        primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(max_length=255)),
                ('servernaam', models.CharField(max_length=255)),
                ('ipadres', models.CharField(max_length=255)),
                ('poort', models.IntegerField()),
                ('scandate', models.DateField()),
                ('scantime', models.TimeField()),
                ('scanmoment', models.DateTimeField()),
                ('rating', models.CharField(max_length=3)),
                ('ratingnotrust', models.CharField(db_column='ratingNoTrust', max_length=3)),
                ('rawdata', models.TextField(db_column='rawData')),
                ('isdead', models.IntegerField(db_column='isDead', default=False)),
                ('isdeadsince', models.DateTimeField(blank=True, db_column='isDeadSince', null=True)),
                ('isdeadreason', models.CharField(blank=True,
                                                  db_column='isDeadReason', max_length=255, null=True)),
            ],
            options={
                'managed': True,
                'db_table': 'scans_ssllabs',
            },
        ),
    ]
