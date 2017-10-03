# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-09-06 09:44
from __future__ import unicode_literals

from django.db import migrations, models

import failmap_admin.organizations.models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0005_auto_20170906_0929'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organization',
            name='twitter_handle',
            field=models.CharField(blank=True, help_text='Include the @ symbol. Used in the top lists to let visitors tweet to theorganization to wake them up.',
                                   max_length=150, null=True, validators=[failmap_admin.organizations.models.validate_twitter]),
        ),
    ]
