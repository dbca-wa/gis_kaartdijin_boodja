# Generated by Django 5.0.7 on 2024-08-08 03:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalogue', '0036_catalogueentrypermission_permission'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='catalogueentrypermission',
            name='permission',
        ),
    ]