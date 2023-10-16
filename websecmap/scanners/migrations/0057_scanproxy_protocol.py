# Generated by Django 2.1.5 on 2019-01-10 17:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scanners", "0056_scanproxy"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanproxy",
            name="protocol",
            field=models.CharField(
                default="https", help_text="Whether to see this as a http or https proxy", max_length=10
            ),
        ),
    ]