# Generated by Django 5.0.7 on 2024-08-07 02:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0035_catalogueentry_permission_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='catalogueentrypermission',
            name='permission',
            field=models.IntegerField(choices=[(1, 'None'), (2, 'Read'), (3, 'Read and Write')], default=1),
        ),
    ]
