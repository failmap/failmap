# Generated by Django 2.1.7 on 2019-03-08 13:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pro', '0011_auto_20181220_1902'),
    ]

    operations = [
        migrations.AddField(
            model_name='urllistreport',
            name='endpoint_ok',
            field=models.IntegerField(default=0, help_text='Zero issues on these endpoints.'),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='ok',
            field=models.IntegerField(default=0, help_text='No issues found at all.'),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='ok_endpoints',
            field=models.IntegerField(default=0, help_text='Amount of endpoints with zero issues.'),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='ok_urls',
            field=models.IntegerField(default=0, help_text='Amount of urls with zero issues.'),
        ),
        migrations.AddField(
            model_name='urllistreport',
            name='url_ok',
            field=models.IntegerField(default=0, help_text='Zero issues on these urls.'),
        ),
    ]
