# Generated by Django 2.0.4 on 2018-04-03 15:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hypersh', '0003_auto_20180327_1952'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credential',
            name='last_result',
            field=models.TextField(default='{}'),
        ),
    ]