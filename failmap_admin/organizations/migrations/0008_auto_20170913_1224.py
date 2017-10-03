# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-13 12:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0007_url_created_on'),
    ]

    operations = [
        migrations.AddField(
            model_name='url',
            name='not_resolvable',
            field=models.BooleanField(
                default=False, help_text='Url is not resolvable (anymore) and will not be picked up by scanners anymore.When the url is not resolvable, ratings from the past will still be shown(?)#'),
        ),
        migrations.AddField(
            model_name='url',
            name='not_resolvable_reason',
            field=models.CharField(
                blank=True, help_text='A scanner might find this not resolvable, some details about that are placed here.', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='url',
            name='not_resolvable_since',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
