# Generated by Django 2.2.10 on 2020-08-05 07:19

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0058_organization_surrogate_id'),
        ('scanners', '0072_auto_20200506_1313'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlannedScan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activity', models.CharField(db_index=True, default='', help_text='discover, verify or scan', max_length=10)),
                ('scanner', models.CharField(db_index=True, default='',
                                             help_text='tlsq, dnssec, http_security_headers, plain_http, internet_nl_mail, dnssec, ftp, dns_endpoints', max_length=10)),
                ('state', models.CharField(db_index=True, default='',
                                           help_text='requested, picked_up, finished, error, timeout', max_length=10)),
                ('requested_at_when', models.DateTimeField()),
                ('finished_at_when', models.DateTimeField(help_text='when finished, timeout, error')),
                ('url', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='organizations.Url')),
            ],
        ),
        migrations.CreateModel(
            name='PlannedScanError',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('debug_information', models.CharField(max_length=512)),
                ('planned_scan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scanners.PlannedScan')),
            ],
        ),
    ]