# Generated by Django 2.1.3 on 2018-11-22 15:10

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("scanners", "0051_internetnlscan"),
    ]

    operations = [
        migrations.RenameField(
            model_name="internetnlscan",
            old_name="url",
            new_name="status_url",
        ),
    ]