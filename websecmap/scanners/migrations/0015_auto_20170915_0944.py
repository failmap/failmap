# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-15 09:44
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scanners", "0014_state"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="screenshot",
            name="url",
        ),
        migrations.AddField(
            model_name="screenshot",
            name="endpoint",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="scanners.Endpoint"
            ),
        ),
    ]
