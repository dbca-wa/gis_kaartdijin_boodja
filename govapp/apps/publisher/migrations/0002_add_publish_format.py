# Generated by Django 3.2.16 on 2023-02-08 05:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('publisher', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cddppublishchannel',
            name='format',
            field=models.IntegerField(choices=[(1, 'Geopackage'), (2, 'Shapefile'), (3, 'Geodatabase')], default=1),
            preserve_default=False,
        ),
    ]