# Generated by Django 2.2 on 2019-04-12 11:32

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pro', '0012_auto_20190308_1317'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='creditmutation',
            options={'get_latest_by': 'at_when', 'ordering': ('-at_when',)},
        ),
        migrations.AlterModelOptions(
            name='urllistreport',
            options={'get_latest_by': 'at_when'},
        ),
        migrations.RenameField(
            model_name='creditmutation',
            old_name='when',
            new_name='at_when',
        ),
        migrations.RenameField(
            model_name='urllistreport',
            old_name='when',
            new_name='at_when',
        ),
        migrations.AlterIndexTogether(
            name='urllistreport',
            index_together={('at_when', 'id')},
        ),
    ]
