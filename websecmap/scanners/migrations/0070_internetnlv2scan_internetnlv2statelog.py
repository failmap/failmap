# Generated by Django 2.2.10 on 2020-05-06 08:32

import django.db.models.deletion
import jsonfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0058_organization_surrogate_id'),
        ('scanners', '0069_scanproxy_last_claim_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='InternetNLV2Scan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(blank=True, help_text='mail, mail_dashboard or web', max_length=30, null=True)),
                ('scan_id', models.CharField(
                    blank=True, help_text='The scan ID that is used to request status and report information.', max_length=32, null=True)),
                ('state', models.CharField(
                    blank=True, help_text='where the scan is: registered, scanning, creating_report, finished, failed', max_length=200, null=True)),
                ('state_message', models.CharField(blank=True,
                                                   help_text='Information about the status, for example error information.', max_length=200, null=True)),
                ('last_state_check', models.DateTimeField(blank=True, null=True)),
                ('metadata', jsonfield.fields.JSONField()),
                ('retrieved_scan_report', jsonfield.fields.JSONField()),
                ('subject_urls', models.ManyToManyField(to='organizations.Url')),
            ],
        ),
        migrations.CreateModel(
            name='InternetNLV2StateLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('state', models.CharField(blank=True, default='',
                                           help_text='The state that was registered at a certain moment in time.', max_length=255)),
                ('state_message', models.CharField(blank=True,
                                                   help_text='Information about the status, for example error information.', max_length=200, null=True)),
                ('last_state_check', models.DateTimeField(blank=True, null=True)),
                ('at_when', models.DateTimeField(blank=True, null=True)),
                ('scan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='scanners.InternetNLV2Scan')),
            ],
        ),
    ]
