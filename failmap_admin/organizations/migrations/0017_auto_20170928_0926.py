# -*- coding: utf-8 -*-
# Generated by Django 1.11.5 on 2017-09-28 09:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0016_auto_20170927_1334'),
    ]

    operations = [
        migrations.AddField(
            model_name='url',
            name='onboarded',
            field=models.BooleanField(default=False, help_text='After adding a url, there is an onboarding process that runs a set of tests.These tests are usually run very quickly to get a first glimpse of the url.This test is run once.'),
        ),
        migrations.AddField(
            model_name='url',
            name='onboarded_on',
            field=models.DateTimeField(auto_now_add=True, help_text='The moment the onboard process finished.', null=True),
        ),
    ]
