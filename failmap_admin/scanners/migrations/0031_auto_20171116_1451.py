# -*- coding: utf-8 -*-
# Generated by Django 1.11.6 on 2017-11-16 14:51
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scanners', '0030_auto_20171113_1240'),
    ]

    operations = [
        migrations.RenameField(
            model_name='tlsqualysscan',
            old_name='scan_moment',
            new_name='last_scan_moment',
        ),
    ]