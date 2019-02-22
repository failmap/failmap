# Generated by Django 2.0.8 on 2018-09-26 10:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hypersh', '0009_auto_20180925_1502'),
    ]

    operations = [
        migrations.AddField(
            model_name='containerconfiguration',
            name='requires_unique_ip',
            field=models.BooleanField(
                default=False, help_text='When set to true, a FIP is connected to this container. Make sure those are available.'),
        ),
        migrations.AlterField(
            model_name='containerconfiguration',
            name='instance_type',
            field=models.CharField(
                default='S1', help_text='Container sizes are described here: https://hyper.sh/hyper/pricing.html - In most cases S3 will suffice. The smaller, the cheaper.', max_length=2),
        ),
    ]