# Generated by Django 5.0.7 on 2024-10-17 03:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0052_alter_geoserverlayerhealthcheck_health_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='geoserverpool',
            name='url',
            field=models.CharField(max_length=500),
        ),
    ]
