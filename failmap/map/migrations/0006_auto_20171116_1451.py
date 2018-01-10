# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-11-16 14:51
from __future__ import unicode_literals

import jsonfield.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('map', '0005_auto_20171013_1004'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organizationrating',
            name='calculation',
            field=jsonfield.fields.JSONField(
                default=dict, help_text='Contains JSON with a calculation of all scanners at this moment, for all urls of this organization. This can be a lot.'),
        ),
        migrations.AlterField(
            model_name='urlrating',
            name='calculation',
            field=jsonfield.fields.JSONField(
                default=dict, help_text='Contains JSON with a calculation of all scanners at this moment. The rating can be spread out over multiple endpoints, which might look a bit confusing. Yet it is perfectly possible as some urls change their IP every five minutes and scans are spread out over days.'),
        ),
    ]