# Generated by Django 3.2.25 on 2024-07-12 02:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0046_geoserverusergroupservice'),
    ]

    operations = [
        migrations.AddField(
            model_name='geoservergroup',
            name='geoserver_usergroup_service',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='publisher.geoserverusergroupservice'),
        ),
    ]