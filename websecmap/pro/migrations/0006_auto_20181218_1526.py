# Generated by Django 2.1.3 on 2018-12-18 15:26

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0047_auto_20181213_1012'),
        ('scanners', '0055_auto_20181213_1218'),
        ('pro', '0005_auto_20181218_1325'),
    ]

    operations = [
        migrations.CreateModel(
            name='RescanRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cost', models.PositiveIntegerField(blank=True, default=0,
                                                     help_text='A positive number of the amount of credits spent for this re-scan.', null=True)),
                ('scan_type', models.CharField(blank=True, max_length=100, null=True)),
                ('added_on', models.DateTimeField(blank=True, null=True)),
                ('started', models.BooleanField(default=False)),
                ('started_on', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(max_length=20)),
                ('finished', models.BooleanField(default=False)),
                ('finished_on', models.DateTimeField(blank=True, null=True)),
                ('account', models.ForeignKey(help_text='Who owns and manages this urllist.',
                                              on_delete=django.db.models.deletion.CASCADE, to='pro.Account')),
                ('endpoint', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='scanners.Endpoint')),
                ('endpoint_scan', models.ForeignKey(null=True,
                                                    on_delete=django.db.models.deletion.CASCADE, to='scanners.EndpointGenericScan')),
                ('url', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='organizations.Url')),
                ('url_scan', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='scanners.UrlGenericScan')),
            ],
        ),
        migrations.AlterModelOptions(
            name='creditmutation',
            options={'get_latest_by': 'when', 'ordering': ('-when',)},
        ),
    ]
