# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-27 13:34
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0015_auto_20170927_1326'),
    ]

    operations = [
        migrations.AlterField(
            model_name='url',
            name='organization_old',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, to='organizations.Organization'),
        ),
    ]
