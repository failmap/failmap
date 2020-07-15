# Generated by Django 2.2.10 on 2020-05-30 14:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pro', '0014_auto_20190604_0922'),
    ]

    operations = [
        migrations.AddField(
            model_name='urllistreport',
            name='endpoint_error_in_test',
            field=models.IntegerField(default=0, help_text='Amount of errors in tests performed on this endpoint.'),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='error_in_test',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='url_error_in_test',
            field=models.IntegerField(default=0, help_text='Amount of errors in tests on this url.'),
        ),
    ]