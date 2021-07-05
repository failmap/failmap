# Generated by Django 2.2.10 on 2020-09-07 07:41

import jsonfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scanners", "0078_auto_20200824_1759"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlannedScanStatistic",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at_when", models.DateTimeField()),
                ("data", jsonfield.fields.JSONField()),
            ],
        ),
    ]
