# Generated by Django 2.0.4 on 2018-04-10 06:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0006_auto_20180410_0644'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationsubmission',
            name='organization_wikipedia',
            field=models.URLField(blank=True, help_text='Helps finding more info about the organization.', null=True),
        ),
    ]